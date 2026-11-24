"""Tableau de bord de l'organisation : chiffres de tous les projets, filtrés par période,
zone, lieu, projet et type de bénéficiaires."""

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Date, Numeric, cast, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models import (
    ActivityExecution,
    BudgetLine,
    ExecutionStatus,
    Expense,
    Project,
    ProjectStatus,
)
from app.schemas.dashboard import (
    Beneficiary,
    Breakdown,
    DashboardOptions,
    DashboardProject,
    OrgDashboard,
    People,
    Spending,
)

CATEGORIES = ("women", "men", "girls", "boys")
# Dans une vue restreinte à un lieu ou à un type de bénéficiaires, un effectif de 1 à 4 peut
# désigner des personnes reconnaissables (« 2 personnes handicapées à Kiwanja ») : il est caché.
SMALL_COUNT = 5


def _hidden(count: int) -> bool:
    return 0 < count < SMALL_COUNT


@dataclass
class Filters:
    year: int | None = None
    month: int | None = None
    zone: str = ""
    location: str = ""
    project_id: UUID | None = None
    beneficiary: Beneficiary | None = None

    def in_period(self, day: date) -> bool:
        return (self.year is None or day.year == self.year) and (
            self.month is None or day.month == self.month
        )


@dataclass
class ExpenseRow:
    """Dépenses d'un projet sur un mois (`spent_on` : premier jour du mois)."""

    project_id: UUID
    amount: Decimal
    spent_on: date


@dataclass
class ExecutionGroup:
    """Activités réalisées d'un projet, d'un mois et d'un lieu, additionnées par la base."""

    project_id: UUID
    start_date: date  # premier jour du mois
    location: str
    completed: bool
    executions: int
    participants: dict[str, int]


def _participants(key: str) -> ColumnElement[Any]:
    """Effectif d'une catégorie (clé du JSON `participants`), NULL s'il n'est pas renseigné."""
    return cast(func.jsonb_extract_path_text(ActivityExecution.participants, key), Numeric)


def _count(key: str) -> ColumnElement[Any]:
    value = _participants(key)
    return cast(func.coalesce(func.sum(func.trunc(value)), 0), Numeric)


def _month(column: Any) -> ColumnElement[date]:
    return cast(func.date_trunc(literal_column("'month'"), column), Date)


async def execution_groups(
    session: AsyncSession, org_id: UUID, beneficiary: Beneficiary | None = None
) -> list[ExecutionGroup]:
    """Une ligne par (projet, mois, lieu, terminée ou non) au lieu d'une par activité réalisée.

    Avec `beneficiary`, seules comptent les activités qui ont touché ce type de bénéficiaires.
    """
    keys = (*CATEGORIES, "with_disability")
    query = (
        select(
            ActivityExecution.project_id,
            _month(ActivityExecution.start_date).label("month"),
            func.btrim(ActivityExecution.location).label("place"),
            (ActivityExecution.status == ExecutionStatus.COMPLETED).label("completed"),
            func.count().label("executions"),
            *(_count(key).label(key) for key in keys),
        )
        .where(ActivityExecution.organization_id == org_id)
        .group_by(ActivityExecution.project_id, "month", "place", "completed")
    )
    if beneficiary:
        query = query.where(_participants(beneficiary) >= 1)
    return [
        ExecutionGroup(
            project_id=row.project_id,
            start_date=row.month,
            location=row.place,
            completed=row.completed,
            executions=row.executions,
            participants={key: int(getattr(row, key)) for key in keys},
        )
        for row in await session.execute(query)
    ]


async def expense_months(session: AsyncSession, org_id: UUID) -> list[ExpenseRow]:
    """Dépenses additionnées par projet et par mois."""
    query = (
        select(
            BudgetLine.project_id,
            _month(Expense.spent_on).label("month"),
            func.sum(Expense.amount).label("amount"),
        )
        .join(Expense.budget_line)
        .where(Expense.organization_id == org_id)
        .group_by(BudgetLine.project_id, "month")
    )
    return [
        ExpenseRow(project_id=row.project_id, amount=row.amount, spent_on=row.month)
        for row in await session.execute(query)
    ]


def _people(group: ExecutionGroup, beneficiary: Beneficiary | None) -> int:
    counts = group.participants
    if beneficiary:
        return counts.get(beneficiary, 0)
    return sum(counts.get(c, 0) for c in CATEGORIES)


def _location(group: ExecutionGroup) -> str:
    return group.location.strip() or "—"


def build_dashboard(
    projects: list[Project],
    executions: list[ExecutionGroup],
    expenses: list[ExpenseRow],
    filters: Filters,
    matching: list[ExecutionGroup] | None = None,
) -> OrgDashboard:
    """`executions` : tous les groupes de l'organisation (ils donnent les choix des filtres).
    `matching` : les groupes restreints au type de bénéficiaires demandé, quand il y en a un."""
    years = {e.start_date.year for e in executions} | {x.spent_on.year for x in expenses}
    options = DashboardOptions(
        years=sorted(years, reverse=True),
        zones=sorted({z.strip() for p in projects for z in p.zones if z.strip()}),
        locations=sorted({e.location.strip() for e in executions if e.location.strip()}),
        projects=[
            DashboardProject(id=p.id, code=p.code, title=p.title)
            for p in sorted(projects, key=lambda p: p.code)
        ],
    )

    kept = [
        p
        for p in projects
        if (filters.project_id is None or p.id == filters.project_id)
        and (not filters.zone or filters.zone in [z.strip() for z in p.zones])
    ]
    by_id = {p.id: p for p in kept}
    selected = [
        e
        for e in (executions if matching is None else matching)
        if e.project_id in by_id
        and filters.in_period(e.start_date)
        and (not filters.location or _location(e) == filters.location)
    ]

    people = People()
    for e in selected:
        for category in (*CATEGORIES, "with_disability"):
            setattr(people, category, getattr(people, category) + e.participants.get(category, 0))
    people.total = (
        getattr(people, filters.beneficiary)
        if filters.beneficiary
        else sum(getattr(people, c) for c in CATEGORIES)
    )

    def breakdown(
        key_of: Callable[[ExecutionGroup], list[str]], label_of: Callable[[str], str]
    ) -> list[Breakdown]:
        rows: dict[str, Breakdown] = {}
        for e in selected:
            for key in key_of(e):
                row = rows.setdefault(key, Breakdown(key=key, label=label_of(key)))
                row.executions += e.executions
                row.people += _people(e, filters.beneficiary)
        return list(rows.values())

    by_month = sorted(
        breakdown(lambda e: [e.start_date.strftime("%Y-%m")], lambda k: k), key=lambda r: r.key
    )
    by_location = sorted(
        breakdown(lambda e: [_location(e)], lambda k: k), key=lambda r: (-r.people, r.label)
    )
    by_zone = sorted(
        breakdown(
            lambda e: [z.strip() for z in by_id[e.project_id].zones if z.strip()] or ["—"],
            lambda k: k,
        ),
        key=lambda r: (-r.people, r.label),
    )
    by_project = sorted(
        breakdown(
            lambda e: [str(e.project_id)],
            lambda k: f"{by_id[UUID(k)].code} {by_id[UUID(k)].title}".strip(),
        ),
        key=lambda r: (-r.people, r.label),
    )

    # Les montants restent dans la devise de chaque projet : pas d'addition entre devises.
    spending: dict[str, Decimal] = defaultdict(Decimal)
    if not filters.location and not filters.beneficiary:
        for x in expenses:
            if x.project_id in by_id and filters.in_period(x.spent_on):
                spending[by_id[x.project_id].currency] += x.amount

    if filters.location or filters.beneficiary:
        for row in (*by_month, *by_location, *by_zone, *by_project):
            if _hidden(row.people):
                row.people, row.masked = 0, True
        for category in (*CATEGORIES, "with_disability", "total"):
            if _hidden(getattr(people, category)):
                setattr(people, category, 0)
                people.masked.append(category)

    return OrgDashboard(
        options=options,
        projects=len(kept),
        active_projects=sum(p.status == ProjectStatus.ACTIVE for p in kept),
        executions=sum(e.executions for e in selected),
        completed_executions=sum(e.executions for e in selected if e.completed),
        people=people,
        spending=[Spending(currency=c, amount=a) for c, a in sorted(spending.items())],
        by_month=by_month,
        by_location=by_location,
        by_zone=by_zone,
        by_project=by_project,
    )
