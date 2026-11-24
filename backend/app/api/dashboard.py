"""Tableau de bord de l'organisation, tous projets confondus."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import AnyMember, SessionDep
from app.models import Project
from app.schemas.dashboard import Beneficiary, OrgDashboard
from app.services.dashboard import Filters, build_dashboard, execution_groups, expense_months

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
    # La base additionne par projet, mois et lieu : l'API ne charge plus chaque activité réalisée.
    executions = await execution_groups(session, org_id)
    matching = await execution_groups(session, org_id, beneficiary) if beneficiary else None
    expenses = await expense_months(session, org_id)
    filters = Filters(
        year=year,
        month=month,
        zone=zone,
        location=location,
        project_id=project_id,
        beneficiary=beneficiary,
    )
    return build_dashboard(projects, executions, expenses, filters, matching)
