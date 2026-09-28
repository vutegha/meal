"""Rapports périodiques et bailleur : création, rédaction IA, édition, validation, export."""

import asyncio
import re
import unicodedata
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.api.deps import AnyMember, SessionDep
from app.api.projects import Planner, ProjectAdmin, _log
from app.documents.render import to_docx, to_pdf
from app.models import Job, PeriodicReport, PeriodicReportVersion, ReportStatus
from app.schemas.accountability import PeriodicIn, PeriodicOut, PeriodicSummary
from app.schemas.ai import JobOut
from app.schemas.tor import TorReview, TorUpdate, TorVersionOut
from app.services import periodic as periodic_svc
from app.services import projects as svc
from app.services import templates, workflow
from app.services.jobs import enqueue
from app.services.tor import TO_COMPLETE

router = APIRouter(prefix="/orgs/{org_id}/projects/{project_id}", tags=["rapports périodiques"])

MEDIA_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}


@router.get("/periodic-reports", response_model=list[PeriodicSummary])
async def list_periodic(
    org_id: UUID, project_id: UUID, _: AnyMember, session: SessionDep
) -> list[PeriodicReport]:
    project = await svc.get_project(session, org_id, project_id)
    rows = await session.scalars(
        select(PeriodicReport)
        .where(PeriodicReport.project_id == project.id)
        .order_by(PeriodicReport.period_end.desc(), PeriodicReport.created_at.desc())
    )
    return list(rows)


@router.post("/periodic-reports", response_model=PeriodicOut, status_code=201)
async def create_periodic(
    org_id: UUID, project_id: UUID, body: PeriodicIn, member: Planner, session: SessionDep
) -> PeriodicReport:
    """Crée le rapport avec ses tableaux calculés ; la rédaction IA est une étape à part."""
    project = await svc.get_project(session, org_id, project_id)
    computed = await periodic_svc.computed_sections(
        session, project, body.period_start, body.period_end
    )
    plan = await templates.resolve(
        session, project, "periodic", periodic_svc.PERIODIC_SECTIONS, body.template_id
    )
    report = PeriodicReport(
        organization_id=org_id,
        project_id=project.id,
        kind=body.kind,
        period_start=body.period_start,
        period_end=body.period_end,
        instructions=body.instructions,
        title=periodic_svc.default_title(body.kind, body.period_start, body.period_end),
        sections=templates.assemble(plan, computed, TO_COMPLETE),
        template_id=plan.template_id,
        created_by=member.user_id,
    )
    session.add(report)
    await session.flush()
    periodic_svc.snapshot(session, report, member.user_id, "Création")
    _log(session, member, "periodic.created", "periodic_report", report.id, {"title": report.title})
    await session.commit()
    await session.refresh(report)
    return report


@router.post(
    "/periodic-reports/{report_id}/generate",
    response_model=JobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_periodic(
    org_id: UUID, project_id: UUID, report_id: UUID, member: Planner, session: SessionDep
) -> Job:
    project = await svc.get_project(session, org_id, project_id)
    report = await periodic_svc.get_periodic(session, project, report_id)
    if report.status != ReportStatus.DRAFT:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Ce rapport est soumis ou approuvé : repassez-le en brouillon d'abord",
        )
    job = Job(
        organization_id=org_id,
        project_id=project.id,
        kind="periodic_generation",
        params={"report_id": str(report.id)},
        created_by=member.user_id,
    )
    session.add(job)
    await session.flush()
    _log(session, member, "ai.periodic_generation_started", "job", job.id, {"title": report.title})
    await session.commit()
    await enqueue(job)
    await session.refresh(job)
    return job


@router.get("/periodic-reports/{report_id}", response_model=PeriodicOut)
async def get_periodic(
    org_id: UUID, project_id: UUID, report_id: UUID, _: AnyMember, session: SessionDep
) -> PeriodicReport:
    project = await svc.get_project(session, org_id, project_id)
    return await periodic_svc.get_periodic(session, project, report_id)


@router.put("/periodic-reports/{report_id}", response_model=PeriodicOut)
async def update_periodic(
    org_id: UUID,
    project_id: UUID,
    report_id: UUID,
    body: TorUpdate,
    member: Planner,
    session: SessionDep,
) -> PeriodicReport:
    project = await svc.get_project(session, org_id, project_id)
    report = await periodic_svc.get_periodic(session, project, report_id)
    if report.status != ReportStatus.DRAFT:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Seuls les rapports en brouillon peuvent être modifiés"
        )
    sections = [s.model_dump() for s in body.sections]
    if body.title == report.title and sections == report.sections:
        return report
    report.title, report.sections = body.title, sections
    report.version += 1
    periodic_svc.snapshot(session, report, member.user_id, "Modification")
    _log(session, member, "periodic.updated", "periodic_report", report.id, {"title": report.title})
    await session.commit()
    await session.refresh(report)
    return report


@router.post("/periodic-reports/{report_id}/refresh", response_model=PeriodicOut)
async def refresh_tables(
    org_id: UUID, project_id: UUID, report_id: UUID, member: Planner, session: SessionDep
) -> PeriodicReport:
    """Recalcule les tableaux (activités, indicateurs, budget) avec les données actuelles."""
    project = await svc.get_project(session, org_id, project_id)
    report = await periodic_svc.get_periodic(session, project, report_id)
    if report.status != ReportStatus.DRAFT:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Seuls les rapports en brouillon peuvent être modifiés"
        )
    computed = await periodic_svc.computed_sections(
        session, project, report.period_start, report.period_end
    )
    sections = [{**s, "content": computed.get(s["key"], s["content"])} for s in report.sections]
    if sections != report.sections:
        report.sections = sections
        report.version += 1
        periodic_svc.snapshot(session, report, member.user_id, "Tableaux recalculés")
        _log(
            session,
            member,
            "periodic.updated",
            "periodic_report",
            report.id,
            {"title": report.title},
        )
        await session.commit()
        await session.refresh(report)
    return report


@router.post("/periodic-reports/{report_id}/{action}", response_model=PeriodicOut)
async def transition_periodic(
    org_id: UUID,
    project_id: UUID,
    report_id: UUID,
    action: str,
    member: Planner,
    session: SessionDep,
    body: TorReview | None = None,
) -> PeriodicReport:
    project = await svc.get_project(session, org_id, project_id)
    report = await periodic_svc.get_periodic(session, project, report_id)
    verb = workflow.transition(report, action, member, body.comment if body else "")
    _log(session, member, f"periodic.{verb}", "periodic_report", report.id, {"title": report.title})
    await session.commit()
    await session.refresh(report)
    return report


@router.delete("/periodic-reports/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_periodic(
    org_id: UUID, project_id: UUID, report_id: UUID, member: ProjectAdmin, session: SessionDep
) -> None:
    project = await svc.get_project(session, org_id, project_id)
    report = await periodic_svc.get_periodic(session, project, report_id)
    _log(session, member, "periodic.deleted", "periodic_report", report.id, {"title": report.title})
    await session.delete(report)
    await session.commit()


@router.get("/periodic-reports/{report_id}/versions", response_model=list[TorVersionOut])
async def list_periodic_versions(
    org_id: UUID, project_id: UUID, report_id: UUID, _: AnyMember, session: SessionDep
) -> list[PeriodicReportVersion]:
    project = await svc.get_project(session, org_id, project_id)
    report = await periodic_svc.get_periodic(session, project, report_id)
    rows = await session.scalars(
        select(PeriodicReportVersion)
        .where(PeriodicReportVersion.report_id == report.id)
        .order_by(PeriodicReportVersion.version.desc())
    )
    return list(rows)


@router.get("/periodic-reports/{report_id}/export.{fmt}")
async def export_periodic(
    org_id: UUID, project_id: UUID, report_id: UUID, fmt: str, _: AnyMember, session: SessionDep
) -> Response:
    if fmt not in MEDIA_TYPES:
        raise svc.not_found("Format")
    project = await svc.get_project(session, org_id, project_id)
    report = await periodic_svc.get_periodic(session, project, report_id)
    document = periodic_svc.render_document(project, report)
    document.layout = (
        await templates.layout_for(session, project, "periodic", report.template_id)
        or document.layout
    )
    content = await asyncio.to_thread(to_docx if fmt == "docx" else to_pdf, document)
    ascii_title = unicodedata.normalize("NFKD", report.title).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^A-Za-z0-9]+", "-", ascii_title).strip("-")[:60] or "Rapport"
    return Response(
        content,
        media_type=MEDIA_TYPES[fmt],
        headers={"Content-Disposition": f'attachment; filename="{slug}-v{report.version}.{fmt}"'},
    )
