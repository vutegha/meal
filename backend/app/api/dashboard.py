"""Tableau de bord de l'organisation, tous projets confondus."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import AnyMember, SessionDep
from app.models import ActivityExecution, BudgetLine, Expense, Project
from app.schemas.dashboard import Beneficiary, OrgDashboard
from app.services.dashboard import ExpenseRow, Filters, build_dashboard

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
    executions = list(
        await session.scalars(
            select(ActivityExecution).where(ActivityExecution.organization_id == org_id)
        )
    )
    expenses = [
        ExpenseRow(project_id=project, amount=amount, spent_on=spent_on)
        for project, amount, spent_on in await session.execute(
            select(BudgetLine.project_id, Expense.amount, Expense.spent_on)
            .join(Expense.budget_line)
            .where(Expense.organization_id == org_id)
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
    return build_dashboard(projects, executions, expenses, filters)
