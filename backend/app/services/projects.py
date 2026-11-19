"""Logique métier des projets : arbre du cadre logique, budget et indicateurs."""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import (
    ARRAY,
    Date,
    Integer,
    Numeric,
    Uuid,
    and_,
    column,
    func,
    select,
    type_coerce,
    values,
)
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Aggregation,
    BudgetLine,
    Expense,
    Indicator,
    IndicatorValue,
    LogframeNode,
    NodeLevel,
    Project,
)
from app.schemas.project import (
    ActivityBudget,
    BudgetLineOut,
    BudgetSummary,
    ExchangeRate,
    IndicatorOut,
    NodeTree,
    PeriodProgress,
    PeriodTarget,
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


@dataclass(frozen=True)
class Totals:
    """Valeurs totales (sans désagrégation) d'un indicateur : somme et dernière valeur."""

    total: Decimal
    latest: Decimal


def _from_totals(
    indicator: Indicator, totals: Totals | None, target: Decimal | None
) -> tuple[Decimal | None, float | None]:
    if totals is None:
        return None, None
    if indicator.aggregation == Aggregation.SUM:
        return totals.total, rate(totals.total, target) if target else None
    if target is None:
        return totals.latest, None
    base = indicator.baseline or Decimal(0)
    return totals.latest, rate(totals.latest - base, target - base)


def achievement(
    indicator: Indicator, values: Sequence[IndicatorValue], target: Decimal | None = None
) -> tuple[Decimal | None, float | None]:
    """Valeur atteinte et taux d'atteinte à partir des valeurs totales (sans désagrégation).

    - agrégation `sum` : somme des valeurs, taux = atteint / cible ;
    - agrégation `latest` : dernière valeur, taux = (atteint - référence) / (cible - référence).

    `target` remplace la cible finale (cible d'une période).
    """
    target = indicator.target if target is None else target
    totals = [v for v in values if not v.disaggregation]
    if not totals:
        return _from_totals(indicator, None, target)
    latest = max(totals, key=lambda v: (v.period_end, v.created_at)).value
    return _from_totals(
        indicator, Totals(sum((v.value for v in totals), Decimal(0)), latest), target
    )


# Valeur totale : saisie sans désagrégation (`{}`).
_IS_TOTAL = IndicatorValue.disaggregation == func.jsonb_build_object()


def _latest_value() -> Any:
    ordered = aggregate_order_by(
        IndicatorValue.value, IndicatorValue.period_end.desc(), IndicatorValue.created_at.desc()
    )
    return type_coerce(func.array_agg(ordered), ARRAY(Numeric))[1]


async def indicator_outs(
    session: AsyncSession, indicators: Sequence[Indicator]
) -> list[IndicatorOut]:
    """Indicateurs avec leur avancement, calculé par la base en deux requêtes.

    Les valeurs ne sont jamais chargées une à une : un projet de plusieurs années en accumule
    des dizaines de milliers.
    """
    if not indicators:
        return []
    ids = [i.id for i in indicators]
    overall = {
        row.indicator_id: Totals(row.total, row.latest)
        for row in await session.execute(
            select(
                IndicatorValue.indicator_id,
                func.sum(IndicatorValue.value).label("total"),
                _latest_value().label("latest"),
            )
            .where(IndicatorValue.indicator_id.in_(ids), _IS_TOTAL)
            .group_by(IndicatorValue.indicator_id)
        )
    }
    targets = {
        indicator.id: [PeriodTarget.model_validate(raw) for raw in indicator.period_targets or []]
        for indicator in indicators
    }
    windows = [
        (indicator_id, index, target.period_start, target.period_end)
        for indicator_id, items in targets.items()
        for index, target in enumerate(items)
    ]
    by_period: dict[tuple[UUID, int], Totals] = {}
    if windows:
        window = (
            values(
                column("indicator_id", Uuid),
                column("idx", Integer),
                column("period_start", Date),
                column("period_end", Date),
                name="windows",
            )
            .data(windows)
            .alias("w")
        )
        query = (
            select(
                window.c.indicator_id,
                window.c.idx,
                func.sum(IndicatorValue.value).label("total"),
                _latest_value().label("latest"),
            )
            .join(
                IndicatorValue,
                and_(
                    IndicatorValue.indicator_id == window.c.indicator_id,
                    IndicatorValue.period_start >= window.c.period_start,
                    IndicatorValue.period_end <= window.c.period_end,
                ),
            )
            .where(_IS_TOTAL)
            .group_by(window.c.indicator_id, window.c.idx)
        )
        by_period = {
            (row.indicator_id, row.idx): Totals(row.total, row.latest)
            for row in await session.execute(query)
        }
    outs = []
    for indicator in indicators:
        achieved, achievement_rate = _from_totals(
            indicator, overall.get(indicator.id), indicator.target
        )
        progress = []
        for index, target in enumerate(targets[indicator.id]):
            done, done_rate = _from_totals(
                indicator, by_period.get((indicator.id, index)), target.target
            )
            progress.append(
                PeriodProgress(**target.model_dump(), achieved=done, achievement_rate=done_rate)
            )
        outs.append(
            IndicatorOut.model_validate(
                {
                    **{
                        k: getattr(indicator, k)
                        for k in IndicatorOut.model_fields
                        if k not in ("achieved", "achievement_rate", "period_targets")
                    },
                    "achieved": achieved,
                    "achievement_rate": achievement_rate,
                    "period_targets": progress,
                }
            )
        )
    return outs


async def indicator_out(session: AsyncSession, indicator: Indicator) -> IndicatorOut:
    return (await indicator_outs(session, [indicator]))[0]


# --- Devises ---------------------------------------------------------------


def exchange_rate(project: Project, currency: str, on: date) -> Decimal | None:
    """Taux du projet en vigueur à une date : le plus récent dont `valid_from` la précède."""
    rates = [ExchangeRate.model_validate(r) for r in project.exchange_rates or []]
    valid = [r for r in rates if r.currency == currency and r.valid_from <= on]
    return max(valid, key=lambda r: r.valid_from).rate if valid else None


def convert_expense(
    project: Project, amount: Decimal, currency: str, rate: Decimal | None, spent_on: date
) -> dict[str, Any]:
    """Champs d'une dépense : montant converti dans la devise du projet et trace de l'origine."""
    if not currency or currency == project.currency:
        return {
            "amount": amount.quantize(Decimal("0.01")),
            "currency": "",
            "original_amount": None,
            "exchange_rate": None,
        }
    rate = rate or exchange_rate(project, currency, spent_on)
    if rate is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Taux de change {currency} → {project.currency} manquant au "
            f"{spent_on:%d/%m/%Y} : ajoutez-le au budget du projet ou saisissez-le.",
        )
    return {
        "amount": (amount * rate).quantize(Decimal("0.01")),
        "currency": currency,
        "original_amount": amount,
        "exchange_rate": rate,
    }


async def list_indicators(
    session: AsyncSession, project_id: UUID, *, with_values: bool = False
) -> Sequence[Indicator]:
    """Indicateurs du projet ; `with_values` charge aussi toutes leurs valeurs (rapports)."""
    query = (
        select(Indicator)
        .where(Indicator.project_id == project_id)
        .order_by(Indicator.code, Indicator.created_at)
    )
    if with_values:
        query = query.options(selectinload(Indicator.values))
    return (await session.scalars(query)).all()
