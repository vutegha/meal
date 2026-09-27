"""Logique métier des projets : arbre du cadre logique, budget et indicateurs."""

from collections import defaultdict
from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Aggregation,
    BudgetLine,
    Expense,
    Indicator,
    LogframeNode,
    NodeLevel,
    Project,
)
from app.schemas.project import (
    ActivityBudget,
    BudgetLineOut,
    BudgetSummary,
    IndicatorOut,
    NodeTree,
)

ACTIVITY_LEVELS = (NodeLevel.ACTIVITY, NodeLevel.SUB_ACTIVITY)


def not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} introuvable")


async def get_project(session: AsyncSession, org_id: UUID, project_id: UUID) -> Project:
    project = await session.scalar(
        select(Project).where(Project.id == project_id, Project.organization_id == org_id)
    )
    if project is None:
        raise not_found("Projet")
    return project


async def get_node(session: AsyncSession, project: Project, node_id: UUID) -> LogframeNode:
    node = await session.scalar(
        select(LogframeNode).where(
            LogframeNode.id == node_id, LogframeNode.project_id == project.id
        )
    )
    if node is None:
        raise not_found("Élément du cadre logique")
    return node


async def list_nodes(session: AsyncSession, project_id: UUID) -> Sequence[LogframeNode]:
    return (
        await session.scalars(
            select(LogframeNode)
            .where(LogframeNode.project_id == project_id)
            .order_by(LogframeNode.position, LogframeNode.created_at)
        )
    ).all()


def build_tree(nodes: Sequence[LogframeNode]) -> list[NodeTree]:
    by_parent: dict[UUID | None, list[LogframeNode]] = defaultdict(list)
    for node in nodes:
        by_parent[node.parent_id].append(node)

    def branch(parent_id: UUID | None) -> list[NodeTree]:
        return [
            NodeTree.model_validate(node).model_copy(update={"children": branch(node.id)})
            for node in by_parent.get(parent_id, [])
        ]

    return branch(None)


async def next_position(session: AsyncSession, project_id: UUID, parent_id: UUID | None) -> int:
    same_parent = (
        LogframeNode.parent_id.is_(None)
        if parent_id is None
        else LogframeNode.parent_id == parent_id
    )
    current = await session.scalar(
        select(func.max(LogframeNode.position)).where(
            LogframeNode.project_id == project_id, same_parent
        )
    )
    return 0 if current is None else current + 1


# --- Budget -----------------------------------------------------------------


async def spent_by_line(session: AsyncSession, project_id: UUID) -> dict[UUID, Decimal]:
    rows = await session.execute(
        select(Expense.budget_line_id, func.sum(Expense.amount))
        .join(BudgetLine)
        .where(BudgetLine.project_id == project_id)
        .group_by(Expense.budget_line_id)
    )
    return {line_id: total for line_id, total in rows}


def budget_line_out(line: BudgetLine, spent: Decimal | None) -> BudgetLineOut:
    return BudgetLineOut.model_validate(line).model_copy(update={"spent": spent or Decimal(0)})


def rate(done: Decimal, planned: Decimal) -> float | None:
    return round(float(done / planned), 4) if planned else None


async def budget_summary(session: AsyncSession, project: Project) -> BudgetSummary:
    lines = (
        await session.scalars(select(BudgetLine).where(BudgetLine.project_id == project.id))
    ).all()
    spent = await spent_by_line(session, project.id)
    nodes = {n.id: n for n in await list_nodes(session, project.id)}

    planned_by: dict[UUID | None, Decimal] = defaultdict(Decimal)
    spent_by: dict[UUID | None, Decimal] = defaultdict(Decimal)
    over = 0
    for line in lines:
        line_spent = spent.get(line.id, Decimal(0))
        planned_by[line.activity_id] += line.planned
        spent_by[line.activity_id] += line_spent
        over += line_spent > line.planned

    by_activity = [
        ActivityBudget(
            activity_id=activity_id,
            code=nodes[activity_id].code if activity_id else "",
            title=nodes[activity_id].title if activity_id else "Coûts de support",
            planned=planned,
            spent=spent_by[activity_id],
            execution_rate=rate(spent_by[activity_id], planned),
        )
        for activity_id, planned in planned_by.items()
    ]
    by_activity.sort(key=lambda a: (a.activity_id is None, a.code, a.title))
    total_planned = sum(planned_by.values(), Decimal(0))
    total_spent = sum(spent_by.values(), Decimal(0))
    return BudgetSummary(
        currency=project.currency,
        planned=total_planned,
        spent=total_spent,
        execution_rate=rate(total_spent, total_planned),
        over_budget_lines=over,
        by_activity=by_activity,
    )


# --- Indicateurs -----------------------------------------------------------


def indicator_out(indicator: Indicator) -> IndicatorOut:
    """Calcule la valeur atteinte à partir des valeurs totales (sans désagrégation).

    - agrégation `sum` : somme des valeurs, taux = atteint / cible ;
    - agrégation `latest` : dernière valeur, taux = (atteint - référence) / (cible - référence).
    """
    totals = [v for v in indicator.values if not v.disaggregation]
    achieved: Decimal | None = None
    achievement: float | None = None
    if totals:
        if indicator.aggregation == Aggregation.SUM:
            achieved = sum((v.value for v in totals), Decimal(0))
            achievement = rate(achieved, indicator.target) if indicator.target else None
        else:
            achieved = max(totals, key=lambda v: (v.period_end, v.created_at)).value
            if indicator.target is not None:
                base = indicator.baseline or Decimal(0)
                achievement = rate(achieved - base, indicator.target - base)
    return IndicatorOut.model_validate(indicator).model_copy(
        update={"achieved": achieved, "achievement_rate": achievement}
    )


async def list_indicators(session: AsyncSession, project_id: UUID) -> Sequence[Indicator]:
    return (
        await session.scalars(
            select(Indicator)
            .where(Indicator.project_id == project_id)
            .options(selectinload(Indicator.values))
            .order_by(Indicator.code, Indicator.created_at)
        )
    ).all()
