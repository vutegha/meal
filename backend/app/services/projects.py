"""Logique métier des projets : arbre du cadre logique, budget et indicateurs."""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import Uuid, bindparam, func, select, text
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
    """Agrégat des valeurs totales (sans désagrégation) d'un indicateur ou d'une période."""

    count: int
    total: Decimal
    latest: Decimal | None


@dataclass
class IndicatorTotals:
    """Agrégats calculés par la base pour les indicateurs d'un projet."""

    overall: dict[UUID, Totals] = field(default_factory=dict)
    # Clé : (indicateur, rang de la cible dans `period_targets`, à partir de 0).
    periods: dict[tuple[UUID, int], Totals] = field(default_factory=dict)


def _totals(values: Sequence[IndicatorValue]) -> Totals | None:
    totals = [v for v in values if not v.disaggregation]
    if not totals:
        return None
    return Totals(
        count=len(totals),
        total=sum((v.value for v in totals), Decimal(0)),
        latest=max(totals, key=lambda v: (v.period_end, v.created_at)).value,
    )


def achievement_from(
    indicator: Indicator, totals: Totals | None, target: Decimal | None = None
) -> tuple[Decimal | None, float | None]:
    """Valeur atteinte et taux d'atteinte à partir de l'agrégat des valeurs totales.

    - agrégation `sum` : somme des valeurs, taux = atteint / cible ;
    - agrégation `latest` : dernière valeur, taux = (atteint - référence) / (cible - référence).

    `target` remplace la cible finale (cible d'une période).
    """
    target = indicator.target if target is None else target
    if totals is None or totals.count == 0:
        return None, None
    if indicator.aggregation == Aggregation.SUM:
        achieved = totals.total
        return achieved, rate(achieved, target) if target else None
    achieved = totals.latest
    if achieved is None or target is None:
        return achieved, None
    base = indicator.baseline or Decimal(0)
    return achieved, rate(achieved - base, target - base)


def achievement(
    indicator: Indicator, values: Sequence[IndicatorValue], target: Decimal | None = None
) -> tuple[Decimal | None, float | None]:
    """Comme `achievement_from`, à partir de valeurs déjà chargées (rapports sur une période)."""
    return achievement_from(indicator, _totals(values), target)


# Une ligne par indicateur : la base additionne et trouve la dernière valeur, sans que l'API
# charge les valeurs. `latest` suit le même ordre que `_totals` (fin de période, puis saisie).
_OVERALL_SQL = text(
    """
    SELECT v.indicator_id,
           count(*) AS n,
           sum(v.value) AS total,
           (array_agg(v.value ORDER BY v.period_end DESC, v.created_at DESC))[1] AS latest
    FROM indicator_values v
    JOIN indicators i ON i.id = v.indicator_id
    WHERE i.project_id = :project_id
      AND (CAST(:indicator_id AS uuid) IS NULL OR i.id = CAST(:indicator_id AS uuid))
      AND v.disaggregation = '{}'::jsonb
    GROUP BY v.indicator_id
    """
).bindparams(bindparam("project_id", type_=Uuid), bindparam("indicator_id", type_=Uuid))

# Une ligne par cible de période qui contient au moins une valeur : valeurs saisies entièrement
# dans la période.
_PERIODS_SQL = text(
    """
    SELECT i.id AS indicator_id,
           t.ord,
           count(*) AS n,
           sum(v.value) AS total,
           (array_agg(v.value ORDER BY v.period_end DESC, v.created_at DESC))[1] AS latest
    FROM indicators i
    CROSS JOIN LATERAL jsonb_array_elements(
        CASE WHEN jsonb_typeof(i.period_targets) = 'array' THEN i.period_targets
             ELSE '[]'::jsonb END
    ) WITH ORDINALITY AS t(target, ord)
    JOIN indicator_values v
      ON v.indicator_id = i.id
     AND v.disaggregation = '{}'::jsonb
     AND v.period_start >= (t.target ->> 'period_start')::date
     AND v.period_end <= (t.target ->> 'period_end')::date
    WHERE i.project_id = :project_id
      AND (CAST(:indicator_id AS uuid) IS NULL OR i.id = CAST(:indicator_id AS uuid))
    GROUP BY i.id, t.ord
    """
).bindparams(bindparam("project_id", type_=Uuid), bindparam("indicator_id", type_=Uuid))


async def indicator_totals(
    session: AsyncSession, project_id: UUID, indicator_id: UUID | None = None
) -> IndicatorTotals:
    """Agrégats des indicateurs d'un projet (ou d'un seul), en deux requêtes quel que soit le
    nombre de valeurs saisies."""
    params = {"project_id": project_id, "indicator_id": indicator_id}
    totals = IndicatorTotals()
    for row in await session.execute(_OVERALL_SQL, params):
        totals.overall[row.indicator_id] = Totals(row.n, row.total, row.latest)
    for row in await session.execute(_PERIODS_SQL, params):
        totals.periods[row.indicator_id, row.ord - 1] = Totals(row.n, row.total, row.latest)
    return totals


def period_progress(indicator: Indicator, totals: IndicatorTotals) -> list[PeriodProgress]:
    """Valeur atteinte sur chaque période cible (valeurs saisies entièrement dans la période).

    La cible d'une période s'entend comme l'agrégation : somme de la période (`sum`) ou niveau
    à atteindre en fin de période (`latest`).
    """
    progress = []
    for rank, raw in enumerate(indicator.period_targets or []):
        target = PeriodTarget.model_validate(raw)
        achieved, achievement_rate = achievement_from(
            indicator, totals.periods.get((indicator.id, rank)), target.target
        )
        progress.append(
            PeriodProgress(
                **target.model_dump(), achieved=achieved, achievement_rate=achievement_rate
            )
        )
    return progress


def indicator_out(indicator: Indicator, totals: IndicatorTotals) -> IndicatorOut:
    achieved, achievement_rate = achievement_from(indicator, totals.overall.get(indicator.id))
    return IndicatorOut.model_validate(
        {
            **{
                k: getattr(indicator, k)
                for k in IndicatorOut.model_fields
                if k not in ("achieved", "achievement_rate", "period_targets")
            },
            "achieved": achieved,
            "achievement_rate": achievement_rate,
            "period_targets": period_progress(indicator, totals),
        }
    )


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
    session: AsyncSession, project_id: UUID, with_values: bool = False
) -> Sequence[Indicator]:
    """Indicateurs du projet. Les valeurs ne sont chargées que sur demande (`with_values`) :
    les taux d'atteinte viennent de `indicator_totals`."""
    query = (
        select(Indicator)
        .where(Indicator.project_id == project_id)
        .order_by(Indicator.code, Indicator.created_at)
    )
    if with_values:
        query = query.options(selectinload(Indicator.values))
    return (await session.scalars(query)).all()


async def indicators_out(session: AsyncSession, project_id: UUID) -> list[IndicatorOut]:
    indicators = await list_indicators(session, project_id)
    totals = await indicator_totals(session, project_id)
    return [indicator_out(i, totals) for i in indicators]
