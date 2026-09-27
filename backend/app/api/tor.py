"""Termes de référence : création, génération IA, édition, circuit de validation, export."""

import asyncio
import re
import unicodedata
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.api.deps import AnyMember, SessionDep
from app.api.projects import Planner, ProjectAdmin, _log
from app.documents.render import to_docx, to_pdf
from app.models import Job, TermsOfReference, TorStatus, TorVersion
from app.schemas.ai import JobOut
from app.schemas.tor import (
    GenerateTorIn,
    TorOut,
    TorReview,
    TorSummary,
    TorUpdate,
    TorVersionOut,
)
from app.services import projects as svc
from app.services import tor as tor_svc
from app.services.jobs import enqueue

router = APIRouter(prefix="/orgs/{org_id}/projects/{project_id}", tags=["TdR"])

MEDIA_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}


def _conflict(message: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, message)


def _require(tor: TermsOfReference, expected: TorStatus, message: str) -> None:
    if tor.status != expected:
        raise _conflict(message)


@router.get("/tors", response_model=list[TorSummary])
async def list_tors(
    org_id: UUID, project_id: UUID, _: AnyMember, session: SessionDep
) -> list[TermsOfReference]:
    project = await svc.get_project(session, org_id, project_id)
    rows = await session.scalars(
        select(TermsOfReference)
        .where(TermsOfReference.project_id == project.id)
        .order_by(TermsOfReference.created_at)
    )
    return list(rows)


@router.post(
    "/activities/{activity_id}/tor", response_model=TorOut, status_code=status.HTTP_201_CREATED
)
async def create_tor(
    org_id: UUID, project_id: UUID, activity_id: UUID, member: Planner, session: SessionDep
) -> TermsOfReference:
    """Crée des TdR vierges, avec les sections du modèle et le budget de l'activité."""
    project = await svc.get_project(session, org_id, project_id)
    activity = await tor_svc.get_activity(session, project, activity_id)
    existing = await session.scalar(
        select(TermsOfReference.id).where(TermsOfReference.activity_id == activity.id)
    )
    if existing:
        raise _conflict("Cette activité a déjà des TdR")
    sections = tor_svc.blank_sections()
    budget = tor_svc.budget_markdown(
        await tor_svc.activity_lines(session, activity), project.currency
    )
    for section in sections:
        if section["key"] == tor_svc.BUDGET_KEY:
            section["content"] = budget
    tor = TermsOfReference(
        organization_id=org_id,
        project_id=project.id,
        activity_id=activity.id,
        title=f"TdR : {activity.title}"[:300],
        sections=sections,
        created_by=member.user_id,
    )
    session.add(tor)
    await session.flush()
    tor_svc.snapshot(session, tor, member.user_id, "Création")
    _log(session, member, "tor.created", "tor", tor.id, {"title": tor.title})
    await session.commit()
    await session.refresh(tor)
    return tor


@router.post(
    "/activities/{activity_id}/tor/generate",
    response_model=JobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_tor(
    org_id: UUID,
    project_id: UUID,
    activity_id: UUID,
    body: GenerateTorIn,
    member: Planner,
    session: SessionDep,
) -> Job:
    project = await svc.get_project(session, org_id, project_id)
    activity = await tor_svc.get_activity(session, project, activity_id)
    current = await session.scalar(
        select(TermsOfReference.status).where(TermsOfReference.activity_id == activity.id)
    )
    if current not in (None, TorStatus.DRAFT):
        raise _conflict("Ces TdR sont soumis ou approuvés : repassez-les en brouillon d'abord")
    job = Job(
        organization_id=org_id,
        project_id=project.id,
        kind="tor_generation",
        params={"activity_id": str(activity.id), "instructions": body.instructions},
        created_by=member.user_id,
    )
    session.add(job)
    await session.flush()
    _log(session, member, "ai.tor_generation_started", "job", job.id, {"title": activity.title})
    await session.commit()
    await enqueue(job)
    await session.refresh(job)
    return job


@router.get("/tors/{tor_id}", response_model=TorOut)
async def get_tor(
    org_id: UUID, project_id: UUID, tor_id: UUID, _: AnyMember, session: SessionDep
) -> TermsOfReference:
    project = await svc.get_project(session, org_id, project_id)
    return await tor_svc.get_tor(session, project, tor_id)


@router.put("/tors/{tor_id}", response_model=TorOut)
async def update_tor(
    org_id: UUID,
    project_id: UUID,
    tor_id: UUID,
    body: TorUpdate,
    member: Planner,
    session: SessionDep,
) -> TermsOfReference:
    project = await svc.get_project(session, org_id, project_id)
    tor = await tor_svc.get_tor(session, project, tor_id)
    _require(tor, TorStatus.DRAFT, "Seuls les TdR en brouillon peuvent être modifiés")
    sections = [section.model_dump() for section in body.sections]
    if body.title == tor.title and sections == tor.sections:
        return tor
    tor.title, tor.sections = body.title, sections
    tor.version += 1
    tor_svc.snapshot(session, tor, member.user_id, "Modification")
    _log(
        session, member, "tor.updated", "tor", tor.id, {"title": tor.title, "version": tor.version}
    )
    await session.commit()
    await session.refresh(tor)
    return tor


@router.post("/tors/{tor_id}/submit", response_model=TorOut)
async def submit_tor(
    org_id: UUID, project_id: UUID, tor_id: UUID, member: Planner, session: SessionDep
) -> TermsOfReference:
    project = await svc.get_project(session, org_id, project_id)
    tor = await tor_svc.get_tor(session, project, tor_id)
    _require(tor, TorStatus.DRAFT, "Ces TdR ont déjà été soumis")
    tor.status = TorStatus.SUBMITTED
    tor.submitted_by, tor.submitted_at = member.user_id, datetime.now(UTC)
    tor.review_comment = ""
    _log(session, member, "tor.submitted", "tor", tor.id, {"title": tor.title})
    await session.commit()
    await session.refresh(tor)
    return tor


@router.post("/tors/{tor_id}/approve", response_model=TorOut)
async def approve_tor(
    org_id: UUID,
    project_id: UUID,
    tor_id: UUID,
    body: TorReview,
    member: ProjectAdmin,
    session: SessionDep,
) -> TermsOfReference:
    project = await svc.get_project(session, org_id, project_id)
    tor = await tor_svc.get_tor(session, project, tor_id)
    _require(tor, TorStatus.SUBMITTED, "Seuls les TdR soumis peuvent être approuvés")
    tor.status = TorStatus.APPROVED
    tor.approved_by, tor.approved_at = member.user_id, datetime.now(UTC)
    tor.review_comment = body.comment
    _log(session, member, "tor.approved", "tor", tor.id, {"title": tor.title})
    await session.commit()
    await session.refresh(tor)
    return tor


@router.post("/tors/{tor_id}/return", response_model=TorOut)
async def return_tor(
    org_id: UUID,
    project_id: UUID,
    tor_id: UUID,
    body: TorReview,
    member: ProjectAdmin,
    session: SessionDep,
) -> TermsOfReference:
    """Renvoie des TdR soumis en brouillon, avec un commentaire pour leur auteur."""
    project = await svc.get_project(session, org_id, project_id)
    tor = await tor_svc.get_tor(session, project, tor_id)
    _require(tor, TorStatus.SUBMITTED, "Seuls les TdR soumis peuvent être renvoyés")
    if not body.comment.strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Expliquez ce qui doit être revu"
        )
    tor.status = TorStatus.DRAFT
    tor.review_comment = body.comment.strip()
    _log(session, member, "tor.returned", "tor", tor.id, {"title": tor.title})
    await session.commit()
    await session.refresh(tor)
    return tor


@router.post("/tors/{tor_id}/reopen", response_model=TorOut)
async def reopen_tor(
    org_id: UUID, project_id: UUID, tor_id: UUID, member: ProjectAdmin, session: SessionDep
) -> TermsOfReference:
    """Repasse des TdR approuvés en brouillon pour les réviser ; l'approbation est levée."""
    project = await svc.get_project(session, org_id, project_id)
    tor = await tor_svc.get_tor(session, project, tor_id)
    _require(tor, TorStatus.APPROVED, "Seuls les TdR approuvés peuvent être rouverts")
    tor.status = TorStatus.DRAFT
    tor.approved_by = tor.approved_at = None
    _log(session, member, "tor.reopened", "tor", tor.id, {"title": tor.title})
    await session.commit()
    await session.refresh(tor)
    return tor


@router.delete("/tors/{tor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tor(
    org_id: UUID, project_id: UUID, tor_id: UUID, member: ProjectAdmin, session: SessionDep
) -> None:
    project = await svc.get_project(session, org_id, project_id)
    tor = await tor_svc.get_tor(session, project, tor_id)
    _log(session, member, "tor.deleted", "tor", tor.id, {"title": tor.title})
    await session.delete(tor)
    await session.commit()


@router.get("/tors/{tor_id}/versions", response_model=list[TorVersionOut])
async def list_versions(
    org_id: UUID, project_id: UUID, tor_id: UUID, _: AnyMember, session: SessionDep
) -> list[TorVersion]:
    project = await svc.get_project(session, org_id, project_id)
    tor = await tor_svc.get_tor(session, project, tor_id)
    rows = await session.scalars(
        select(TorVersion).where(TorVersion.tor_id == tor.id).order_by(TorVersion.created_at.desc())
    )
    return list(rows)


@router.get("/tors/{tor_id}/export.{fmt}")
async def export_tor(
    org_id: UUID, project_id: UUID, tor_id: UUID, fmt: str, _: AnyMember, session: SessionDep
) -> Response:
    if fmt not in MEDIA_TYPES:
        raise svc.not_found("Format")
    project = await svc.get_project(session, org_id, project_id)
    tor = await tor_svc.get_tor(session, project, tor_id)
    document = await tor_svc.render_document(session, project, tor)
    content = await asyncio.to_thread(to_docx if fmt == "docx" else to_pdf, document)
    ascii_title = unicodedata.normalize("NFKD", tor.title).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^A-Za-z0-9]+", "-", ascii_title).strip("-")[:60] or "TdR"
    return Response(
        content,
        media_type=MEDIA_TYPES[fmt],
        headers={"Content-Disposition": f'attachment; filename="{slug}-v{tor.version}.{fmt}"'},
    )
