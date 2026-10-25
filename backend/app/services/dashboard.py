"""Tableau de bord de l'organisation : chiffres de tous les projets, filtrés par période,
zone, lieu, projet et type de bénéficiaires."""

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.models import ActivityExecution, ExecutionStatus, Project, ProjectStatus
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
    project_id: UUID
    amount: Decimal
    spent_on: date


def _people(execution: ActivityExecution, beneficiary: Beneficiary | None) -> int:
    counts = execution.participants or {}
    if beneficiary:
        return int(counts.get(beneficiary, 0))
    return sum(int(counts.get(c, 0)) for c in CATEGORIES)


def _location(execution: ActivityExecution) -> str:
    return execution.location.strip() or "—"


def build_dashboard(
    projects: list[Project],
    executions: list[ActivityExecution],
    expenses: list[ExpenseRow],
    filters: Filters,
) -> OrgDashboard:
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
        for e in executions
        if e.project_id in by_id
        and filters.in_period(e.start_date)
        and (not filters.location or _location(e) == filters.location)
        and (not filters.beneficiary or _people(e, filters.beneficiary) > 0)
    ]

    people = People()
    for e in selected:
        counts = e.participants or {}
        for category in (*CATEGORIES, "with_disability"):
            setattr(people, category, getattr(people, category) + int(counts.get(category, 0)))
    people.total = (
        getattr(people, filters.beneficiary)
        if filters.beneficiary
        else sum(getattr(people, c) for c in CATEGORIES)
    )

    def breakdown(
        key_of: Callable[[ActivityExecution], list[str]], label_of: Callable[[str], str]
    ) -> list[Breakdown]:
        rows: dict[str, Breakdown] = {}
        for e in selected:
            for key in key_of(e):
                row = rows.setdefault(key, Breakdown(key=key, label=label_of(key)))
                row.executions += 1
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

    return OrgDashboard(
        options=options,
        projects=len(kept),
        active_projects=sum(p.status == ProjectStatus.ACTIVE for p in kept),
        executions=len(selected),
        completed_executions=sum(e.status == ExecutionStatus.COMPLETED for e in selected),
        people=people,
        spending=[Spending(currency=c, amount=a) for c, a in sorted(spending.items())],
        by_month=by_month,
        by_location=by_location,
        by_zone=by_zone,
        by_project=by_project,
    )
