"""Tableau de bord de l'organisation, tous projets confondus."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import Date, Integer, func, select

from app.api.deps import AnyMember, SessionDep
from app.models import ActivityExecution, BudgetLine, Expense, Project
from app.schemas.dashboard import Beneficiary, OrgDashboard
from app.services.dashboard import CATEGORIES, ExpenseRow, Filters, RunGroup, build_dashboard

router = APIRouter(prefix="/orgs/{org_id}", tags=["tableau de bord"])


@router.get("/dashboard", response_model=OrgDashboard)
async def org_dashboard(
    org_id: UUID,
    _: AnyMember,
    session: SessionDep,
    year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
    month: Annotated[int | None, Query(ge=1, le=12)] = None,
    zone: str = "",
    location: str = "",
    project_id: UUID | None = None,
    beneficiary: Beneficiary | None = None,
) -> OrgDashboard:
    projects = list(await session.scalars(select(Project).where(Project.organization_id == org_id)))
    org = ActivityExecution.organization_id == org_id
    run_month = func.date_trunc("month", ActivityExecution.start_date).cast(Date)
    place = func.trim(ActivityExecution.location)
    people = [
        func.coalesce(func.sum(ActivityExecution.participants[key].as_integer()), 0).label(key)
        for key in (*CATEGORIES, "with_disability")
    ]
    runs = (
        select(
            ActivityExecution.project_id,
            run_month.label("month"),
            place.label("location"),
            ActivityExecution.status,
            func.count().label("n"),
            *people,
        )
        .where(org)
        .group_by(ActivityExecution.project_id, run_month, place, ActivityExecution.status)
    )
    if beneficiary:
        # Filtre par exécution, avant le regroupement : comme une exécution prise seule.
        runs = runs.where(ActivityExecution.participants[beneficiary].as_integer() > 0)
    executions = [
        RunGroup(
            project_id=row.project_id,
            start_date=row.month,
            location=row.location,
            status=row.status,
            count=row.n,
            participants={key: getattr(row, key) for key in (*CATEGORIES, "with_disability")},
        )
        for row in await session.execute(runs)
    ]
    years = set(
        await session.scalars(
            select(func.extract("year", ActivityExecution.start_date).cast(Integer))
            .where(org)
            .distinct()
        )
    )
    locations: set[str] = set(await session.scalars(select(place).where(org).distinct()))
    spent_month = func.date_trunc("month", Expense.spent_on).cast(Date)
    expenses = [
        ExpenseRow(project_id=project, amount=amount, spent_on=spent_on)
        for project, spent_on, amount in await session.execute(
            select(BudgetLine.project_id, spent_month, func.sum(Expense.amount))
            .join(Expense.budget_line)
            .where(Expense.organization_id == org_id)
            .group_by(BudgetLine.project_id, spent_month)
        )
    ]
    filters = Filters(
        year=year,
        month=month,
        zone=zone,
        location=location,
        project_id=project_id,
        beneficiary=beneficiary,
    )
    return build_dashboard(projects, executions, expenses, filters, years, locations)
