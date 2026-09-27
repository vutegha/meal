"""Rapports narratifs : génération IA, édition, circuit de validation, indicateurs, export."""

import asyncio
import re
import unicodedata
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.api.deps import AnyMember, SessionDep
from app.api.projects import Collector, Planner, ProjectAdmin, _log
from app.documents.render import to_docx, to_pdf
from app.models import (
    Indicator,
    IndicatorValue,
    Job,
    NarrativeReport,
    ReportStatus,
    ReportVersion,
)
from app.schemas.ai import JobOut
from app.schemas.report import ApplySuggestionIn, ReportOut, ReportSummary
from app.schemas.tor import TorReview, TorUpdate, TorVersionOut
from app.services import projects as svc
from app.services import report as report_svc
from app.services.jobs import enqueue

router = APIRouter(prefix="/orgs/{org_id}/projects/{project_id}", tags=["rapports"])

MEDIA_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}


def _require(report: NarrativeReport, expected: ReportStatus, message: str) -> None:
    if report.status != expected:
        raise HTTPException(status.HTTP_409_CONFLICT, message)


@router.get("/reports", response_model=list[ReportSummary])
async def list_reports(
    org_id: UUID,
    project_id: UUID,
    _: AnyMember,
    session: SessionDep,
    execution_id: UUID | None = None,
) -> list[NarrativeReport]:
    project = await svc.get_project(session, org_id, project_id)
    query = select(NarrativeReport).where(NarrativeReport.project_id == project.id)
    if execution_id:
        query = query.where(NarrativeReport.execution_id == execution_id)
    return list(await session.scalars(query.order_by(NarrativeReport.created_at)))


@router.post(
    "/executions/{execution_id}/report/generate",
    response_model=JobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_report(
    org_id: UUID, project_id: UUID, execution_id: UUID, member: Planner, session: SessionDep
) -> Job:
    project = await svc.get_project(session, org_id, project_id)
    execution = await report_svc.get_execution(session, project, execution_id)
    current = await session.scalar(
        select(NarrativeReport.status).where(NarrativeReport.execution_id == execution.id)
    )
    if current not in (None, ReportStatus.DRAFT):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Ce rapport est soumis ou approuvé : repassez-le en brouillon d'abord",
        )
    job = Job(
        organization_id=org_id,
        project_id=project.id,
        kind="report_generation",
        params={"execution_id": str(execution.id)},
        created_by=member.user_id,
    )
    session.add(job)
    await session.flush()
    _log(session, member, "ai.report_generation_started", "job", job.id, {"title": execution.title})
    await session.commit()
    await enqueue(job)
    await session.refresh(job)
    return job


@router.get("/reports/{report_id}", response_model=ReportOut)
async def get_report(
    org_id: UUID, project_id: UUID, report_id: UUID, _: AnyMember, session: SessionDep
) -> NarrativeReport:
    project = await svc.get_project(session, org_id, project_id)
    return await report_svc.get_report(session, project, report_id)


@router.put("/reports/{report_id}", response_model=ReportOut)
async def update_report(
    org_id: UUID,
    project_id: UUID,
    report_id: UUID,
    body: TorUpdate,
    member: Planner,
    session: SessionDep,
) -> NarrativeReport:
    project = await svc.get_project(session, org_id, project_id)
    report = await report_svc.get_report(session, project, report_id)
    _require(report, ReportStatus.DRAFT, "Seuls les rapports en brouillon peuvent être modifiés")
    sections = [s.model_dump() for s in body.sections]
    if body.title == report.title and sections == report.sections:
        return report
    report.title, report.sections = body.title, sections
    report.version += 1
    report_svc.snapshot(session, report, member.user_id, "Modification")
    _log(session, member, "report.updated", "narrative_report", report.id, {"title": report.title})
    await session.commit()
    await session.refresh(report)
    return report


@router.post("/reports/{report_id}/{action}", response_model=ReportOut)
async def transition_report(
    org_id: UUID,
    project_id: UUID,
    report_id: UUID,
    action: str,
    member: Planner,
    session: SessionDep,
    body: TorReview | None = None,
) -> NarrativeReport:
    """submit (rédacteurs) ; approve, return, reopen (chef de projet ou administrateur)."""
    project = await svc.get_project(session, org_id, project_id)
    report = await report_svc.get_report(session, project, report_id)
    comment = (body.comment if body else "").strip()
    if action != "submit" and member.role.value not in ("admin", "project_manager"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé au chef de projet")
    if action == "submit":
        _require(report, ReportStatus.DRAFT, "Ce rapport a déjà été soumis")
        report.status = ReportStatus.SUBMITTED
        report.submitted_by, report.submitted_at = member.user_id, datetime.now(UTC)
        report.review_comment = ""
    elif action == "approve":
        _require(report, ReportStatus.SUBMITTED, "Seuls les rapports soumis peuvent être approuvés")
        report.status = ReportStatus.APPROVED
        report.approved_by, report.approved_at = member.user_id, datetime.now(UTC)
        report.review_comment = comment
    elif action == "return":
        _require(report, ReportStatus.SUBMITTED, "Seuls les rapports soumis peuvent être renvoyés")
        if not comment:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Expliquez ce qui doit être revu"
            )
        report.status, report.review_comment = ReportStatus.DRAFT, comment
    elif action == "reopen":
        _require(
            report, ReportStatus.APPROVED, "Seuls les rapports approuvés peuvent être rouverts"
        )
        report.status = ReportStatus.DRAFT
        report.approved_by = report.approved_at = None
    else:
        raise svc.not_found("Action")
    verb = {
        "submit": "submitted",
        "approve": "approved",
        "return": "returned",
        "reopen": "reopened",
    }
    _log(
        session,
        member,
        f"report.{verb[action]}",
        "narrative_report",
        report.id,
        {"title": report.title},
    )
    await session.commit()
    await session.refresh(report)
    return report


@router.post("/reports/{report_id}/suggestions/{index}/apply", response_model=ReportOut)
async def apply_suggestion(
    org_id: UUID,
    project_id: UUID,
    report_id: UUID,
    index: int,
    body: ApplySuggestionIn,
    member: Collector,
    session: SessionDep,
) -> NarrativeReport:
    """Enregistre la valeur d'indicateur proposée (ou corrigée), rattachée à l'exécution."""
    project = await svc.get_project(session, org_id, project_id)
    report = await report_svc.get_report(session, project, report_id)
    if not 0 <= index < len(report.indicator_suggestions):
        raise svc.not_found("Proposition")
    suggestion = dict(report.indicator_suggestions[index])
    if suggestion.get("applied_value_id"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Cette valeur a déjà été enregistrée")
    indicator = await session.scalar(
        select(Indicator).where(
            Indicator.id == UUID(suggestion["indicator_id"]), Indicator.project_id == project.id
        )
    )
    if indicator is None:
        raise svc.not_found("Indicateur")
    execution = await report_svc.get_execution(session, project, report.execution_id)
    value = IndicatorValue(
        organization_id=org_id,
        indicator_id=indicator.id,
        period_start=execution.start_date,
        period_end=execution.end_date or execution.start_date,
        value=body.value if body.value is not None else Decimal(suggestion["value"]),
        source=f"{report.title} ({suggestion.get('source_ref') or 'rapport narratif'})",
        recorded_by=member.user_id,
        execution_id=execution.id,
    )
    session.add(value)
    await session.flush()
    suggestion["applied_value_id"] = str(value.id)
    suggestion["value"] = str(value.value)
    suggestions = list(report.indicator_suggestions)
    suggestions[index] = suggestion
    report.indicator_suggestions = suggestions
    _log(
        session,
        member,
        "indicator.value_recorded",
        "indicator_value",
        value.id,
        {"indicator": indicator.name, "value": str(value.value)},
    )
    await session.commit()
    await session.refresh(report)
    return report


@router.delete("/reports/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(
    org_id: UUID, project_id: UUID, report_id: UUID, member: ProjectAdmin, session: SessionDep
) -> None:
    project = await svc.get_project(session, org_id, project_id)
    report = await report_svc.get_report(session, project, report_id)
    _log(session, member, "report.deleted", "narrative_report", report.id, {"title": report.title})
    await session.delete(report)
    await session.commit()


@router.get("/reports/{report_id}/versions", response_model=list[TorVersionOut])
async def list_versions(
    org_id: UUID, project_id: UUID, report_id: UUID, _: AnyMember, session: SessionDep
) -> list[ReportVersion]:
    project = await svc.get_project(session, org_id, project_id)
    report = await report_svc.get_report(session, project, report_id)
    rows = await session.scalars(
        select(ReportVersion)
        .where(ReportVersion.report_id == report.id)
        .order_by(ReportVersion.created_at.desc())
    )
    return list(rows)


@router.get("/reports/{report_id}/export.{fmt}")
async def export_report(
    org_id: UUID, project_id: UUID, report_id: UUID, fmt: str, _: AnyMember, session: SessionDep
) -> Response:
    if fmt not in MEDIA_TYPES:
        raise svc.not_found("Format")
    project = await svc.get_project(session, org_id, project_id)
    report = await report_svc.get_report(session, project, report_id)
    document = await report_svc.render_document(session, project, report)
    content = await asyncio.to_thread(to_docx if fmt == "docx" else to_pdf, document)
    ascii_title = unicodedata.normalize("NFKD", report.title).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^A-Za-z0-9]+", "-", ascii_title).strip("-")[:60] or "Rapport"
    return Response(
        content,
        media_type=MEDIA_TYPES[fmt],
        headers={"Content-Disposition": f'attachment; filename="{slug}-v{report.version}.{fmt}"'},
    )
