"""Exécution des activités : saisie terrain, preuves, dépenses réelles.

Les créations acceptent un `client_uuid` généré par l'application hors ligne : renvoyer la
même saisie (après une coupure réseau) renvoie l'élément existant au lieu de le dupliquer.
"""

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import AnyMember, SessionDep, require_membership
from app.api.projects import Collector, ProjectAdmin, _flush, _log
from app.core.config import get_settings
from app.documents.storage import get_storage
from app.models import (
    ActivityExecution,
    BudgetLine,
    Evidence,
    EvidenceKind,
    Expense,
    LogframeNode,
    Membership,
    Project,
    Role,
)
from app.schemas.execution import (
    EvidenceOut,
    EvidenceUpdate,
    ExecutionDetail,
    ExecutionExpenseIn,
    ExecutionExpenseOut,
    ExecutionIn,
    ExecutionOut,
    ExecutionUpdate,
    Participants,
)
from app.services import projects as svc
from app.services.evidence import UnsupportedFile, media_type, process, render_thumbnail

router = APIRouter(prefix="/orgs/{org_id}/projects/{project_id}", tags=["exécution"])

# Les agents terrain saisissent les dépenses réelles de leurs activités, la finance aussi.
Spender = Annotated[
    Membership,
    Depends(
        require_membership(
            Role.ADMIN, Role.PROJECT_MANAGER, Role.MEAL_OFFICER, Role.FIELD_AGENT, Role.FINANCE
        )
    ),
]


_COMPUTED = {"has_thumbnail", "faces", "blur_faces"}


def evidence_out(evidence: Evidence) -> EvidenceOut:
    extra = evidence.extra or {}
    return EvidenceOut.model_validate(
        {
            **{k: getattr(evidence, k) for k in EvidenceOut.model_fields if k not in _COMPUTED},
            "has_thumbnail": bool(evidence.thumbnail_key),
            "faces": extra.get("faces", 0),
            "blur_faces": extra.get("blur_faces", True),
        }
    )


# Voir les visages d'une photo (original, vignette non floutée) : responsables et suivi-évaluation.
FACE_ROLES = (Role.ADMIN, Role.PROJECT_MANAGER, Role.MEAL_OFFICER)


async def _spent(session: SessionDep, execution_ids: list[UUID]) -> dict[UUID, Decimal]:
    rows = await session.execute(
        select(Expense.execution_id, func.sum(Expense.amount))
        .where(Expense.execution_id.in_(execution_ids))
        .group_by(Expense.execution_id)
    )
    return {execution_id: total for execution_id, total in rows if execution_id}


def execution_out(execution: ActivityExecution, spent: Decimal | None) -> ExecutionOut:
    participants = Participants.model_validate(execution.participants)
    return ExecutionOut.model_validate(
        {
            **{
                k: getattr(execution, k)
                for k in ExecutionOut.model_fields
                if k not in ("participants", "participants_total", "evidence_count", "spent")
            },
            "participants": participants,
            "participants_total": participants.total,
            "evidence_count": len(execution.evidence),
            "spent": spent or Decimal(0),
        }
    )


async def _get_execution(
    session: SessionDep, project: Project, execution_id: UUID
) -> ActivityExecution:
    execution = await session.scalar(
        select(ActivityExecution)
        .where(ActivityExecution.id == execution_id, ActivityExecution.project_id == project.id)
        .options(selectinload(ActivityExecution.evidence))
        .execution_options(populate_existing=True)
    )
    if execution is None:
        raise svc.not_found("Exécution")
    return execution


async def _get_evidence(session: SessionDep, project: Project, evidence_id: UUID) -> Evidence:
    evidence = await session.scalar(
        select(Evidence).where(Evidence.id == evidence_id, Evidence.project_id == project.id)
    )
    if evidence is None:
        raise svc.not_found("Pièce")
    return evidence


async def _detail(session: SessionDep, execution: ActivityExecution) -> ExecutionDetail:
    expenses = list(
        await session.scalars(
            select(Expense)
            .where(Expense.execution_id == execution.id)
            .order_by(Expense.spent_on, Expense.created_at)
        )
    )
    children = select(LogframeNode.id).where(LogframeNode.parent_id == execution.activity_id)
    lines = await session.scalars(
        select(BudgetLine).where(
            (BudgetLine.activity_id == execution.activity_id) | BudgetLine.activity_id.in_(children)
        )
    )
    base = execution_out(execution, sum((e.amount for e in expenses), Decimal(0)))
    return ExecutionDetail(
        **base.model_dump(),
        evidence=[evidence_out(e) for e in execution.evidence],
        expenses=[ExecutionExpenseOut.model_validate(e) for e in expenses],
        planned=sum((line.planned for line in lines), Decimal(0)),
    )


# --- Exécutions ------------------------------------------------------------------


@router.get("/executions", response_model=list[ExecutionOut])
async def list_executions(
    org_id: UUID,
    project_id: UUID,
    _: AnyMember,
    session: SessionDep,
    activity_id: UUID | None = None,
) -> list[ExecutionOut]:
    project = await svc.get_project(session, org_id, project_id)
    query = (
        select(ActivityExecution)
        .where(ActivityExecution.project_id == project.id)
        .options(selectinload(ActivityExecution.evidence))
        .order_by(ActivityExecution.start_date.desc(), ActivityExecution.created_at.desc())
    )
    if activity_id:
        query = query.where(ActivityExecution.activity_id == activity_id)
    executions = list(await session.scalars(query))
    spent = await _spent(session, [e.id for e in executions])
    return [execution_out(e, spent.get(e.id)) for e in executions]


@router.post("/executions", response_model=ExecutionDetail, status_code=status.HTTP_201_CREATED)
async def create_execution(
    org_id: UUID,
    project_id: UUID,
    body: ExecutionIn,
    member: Collector,
    session: SessionDep,
    response: Response,
) -> ExecutionDetail:
    project = await svc.get_project(session, org_id, project_id)
    if body.client_uuid:
        existing = await session.scalar(
            select(ActivityExecution.id).where(
                ActivityExecution.client_uuid == body.client_uuid,
                ActivityExecution.project_id == project.id,
            )
        )
        if existing:
            response.status_code = status.HTTP_200_OK
            return await _detail(session, await _get_execution(session, project, existing))
    activity = await svc.get_node(session, project, body.activity_id)
    if activity.level not in svc.ACTIVITY_LEVELS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Seule une activité peut être exécutée"
        )
    execution = ActivityExecution(
        organization_id=org_id,
        project_id=project.id,
        created_by=member.user_id,
        **body.model_dump(exclude={"participants"}),
        participants=body.participants.model_dump(),
    )
    session.add(execution)
    await _flush(session, "Cette saisie a déjà été envoyée")
    _log(
        session,
        member,
        "execution.created",
        "activity_execution",
        execution.id,
        {"title": execution.title or activity.title, "code": activity.code},
    )
    await session.commit()
    return await _detail(session, await _get_execution(session, project, execution.id))


@router.get("/executions/{execution_id}", response_model=ExecutionDetail)
async def get_execution(
    org_id: UUID, project_id: UUID, execution_id: UUID, _: AnyMember, session: SessionDep
) -> ExecutionDetail:
    project = await svc.get_project(session, org_id, project_id)
    return await _detail(session, await _get_execution(session, project, execution_id))


@router.patch("/executions/{execution_id}", response_model=ExecutionDetail)
async def update_execution(
    org_id: UUID,
    project_id: UUID,
    execution_id: UUID,
    body: ExecutionUpdate,
    member: Collector,
    session: SessionDep,
) -> ExecutionDetail:
    project = await svc.get_project(session, org_id, project_id)
    execution = await _get_execution(session, project, execution_id)
    changes = body.model_dump(exclude_unset=True)
    if "participants" in changes:
        changes["participants"] = body.participants.model_dump() if body.participants else {}
    for field, value in changes.items():
        setattr(execution, field, value)
    if execution.end_date and execution.end_date < execution.start_date:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "La date de fin précède la date de début"
        )
    _log(
        session,
        member,
        "execution.updated",
        "activity_execution",
        execution.id,
        {"fields": sorted(changes)},
    )
    await session.commit()
    return await _detail(session, await _get_execution(session, project, execution_id))


@router.delete("/executions/{execution_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_execution(
    org_id: UUID, project_id: UUID, execution_id: UUID, member: ProjectAdmin, session: SessionDep
) -> None:
    project = await svc.get_project(session, org_id, project_id)
    execution = await _get_execution(session, project, execution_id)
    keys = [k for e in execution.evidence for k in (e.storage_key, e.thumbnail_key) if k]
    _log(
        session,
        member,
        "execution.deleted",
        "activity_execution",
        execution.id,
        {"title": execution.title},
    )
    await session.delete(execution)
    await session.commit()
    storage = get_storage()
    for key in keys:
        await storage.delete(key)


# --- Preuves ---------------------------------------------------------------------


@router.post(
    "/executions/{execution_id}/evidence",
    response_model=EvidenceOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_evidence(
    org_id: UUID,
    project_id: UUID,
    execution_id: UUID,
    file: UploadFile,
    member: Collector,
    session: SessionDep,
    response: Response,
    kind: Annotated[EvidenceKind, Form()] = EvidenceKind.OTHER,
    caption: Annotated[str, Form(max_length=2000)] = "",
    consent_given: Annotated[bool, Form()] = False,
    client_uuid: Annotated[UUID | None, Form()] = None,
    # Date et position lues sur le téléphone : la photo compressée avant envoi a perdu son EXIF,
    # et les vidéos n'en ont pas. Celles du fichier priment.
    taken_at: Annotated[datetime | None, Form()] = None,
    latitude: Annotated[Decimal | None, Form(ge=-90, le=90)] = None,
    longitude: Annotated[Decimal | None, Form(ge=-180, le=180)] = None,
) -> EvidenceOut:
    project = await svc.get_project(session, org_id, project_id)
    execution = await _get_execution(session, project, execution_id)
    if client_uuid:
        existing = await session.scalar(
            select(Evidence).where(
                Evidence.client_uuid == client_uuid, Evidence.project_id == project.id
            )
        )
        if existing:
            response.status_code = status.HTTP_200_OK
            return evidence_out(existing)

    filename = file.filename or "piece"
    settings = get_settings()
    max_mb = (
        settings.max_media_mb if media_type(filename, file.content_type) else settings.max_upload_mb
    )
    data = await file.read(max_mb * 1024 * 1024 + 1)
    if len(data) > max_mb * 1024 * 1024:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, f"Fichier trop volumineux (maximum {max_mb} Mo)"
        )
    try:
        processed = await process(data, filename, file.content_type)
    except UnsupportedFile as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc

    storage = get_storage()
    prefix = f"{org_id}/{project.id}/executions/{execution.id}/{uuid4()}"
    key = f"{prefix}-{filename[-120:]}"
    await storage.put(key, data, processed.content_type)
    thumbnail_key = ""
    if processed.thumbnail:
        thumbnail_key = f"{prefix}-vignette.webp"
        await storage.put(thumbnail_key, processed.thumbnail, "image/webp")
    if processed.is_image and kind == EvidenceKind.OTHER:
        kind = EvidenceKind.PHOTO
    if media := processed.extra.get("media"):
        kind = EvidenceKind(media)
    evidence = Evidence(
        organization_id=org_id,
        project_id=project.id,
        execution_id=execution.id,
        kind=kind,
        filename=filename[:300],
        content_type=processed.content_type,
        size_bytes=len(data),
        sha256=processed.sha256,
        storage_key=key,
        thumbnail_key=thumbnail_key,
        caption=caption,
        taken_at=processed.taken_at or taken_at,
        latitude=processed.latitude if processed.latitude is not None else latitude,
        longitude=processed.longitude if processed.longitude is not None else longitude,
        consent_given=consent_given,
        text=processed.text,
        page_count=processed.page_count,
        uploaded_by=member.user_id,
        client_uuid=client_uuid,
        extra=processed.extra,
    )
    session.add(evidence)
    await _flush(session, "Cette pièce a déjà été envoyée")
    _log(session, member, "evidence.uploaded", "evidence", evidence.id, {"name": evidence.filename})
    await session.commit()
    await session.refresh(evidence)
    return evidence_out(evidence)


@router.patch("/evidence/{evidence_id}", response_model=EvidenceOut)
async def update_evidence(
    org_id: UUID,
    project_id: UUID,
    evidence_id: UUID,
    body: EvidenceUpdate,
    member: Collector,
    session: SessionDep,
) -> EvidenceOut:
    project = await svc.get_project(session, org_id, project_id)
    evidence = await _get_evidence(session, project, evidence_id)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    blur = changes.pop("blur_faces", None)
    for field, value in changes.items():
        setattr(evidence, field, value)
    # Consentement retiré : les visages redeviennent floutés.
    if not evidence.consent_given and not (evidence.extra or {}).get("blur_faces", True):
        await _set_blur(evidence, True, member, force=True)
    elif blur is not None and evidence.thumbnail_key:
        await _set_blur(evidence, blur, member)
    _log(session, member, "evidence.updated", "evidence", evidence.id, {"name": evidence.filename})
    await session.commit()
    await session.refresh(evidence)
    return evidence_out(evidence)


async def _set_blur(
    evidence: Evidence, blur: bool, member: Membership, force: bool = False
) -> None:
    extra = evidence.extra or {}
    if blur == extra.get("blur_faces", True):
        return
    if not force and member.role not in FACE_ROLES:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Seul un responsable peut décider du floutage des visages"
        )
    if not blur and not evidence.consent_given:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Sans consentement des personnes photographiées, les visages restent floutés",
        )
    storage = get_storage()
    try:
        thumbnail, faces = await asyncio.to_thread(
            render_thumbnail, await storage.get(evidence.storage_key), blur
        )
    except UnsupportedFile as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    await storage.put(evidence.thumbnail_key, thumbnail, "image/webp")
    evidence.extra = {**extra, "blur_faces": blur, "faces": faces}


@router.delete("/evidence/{evidence_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_evidence(
    org_id: UUID, project_id: UUID, evidence_id: UUID, member: Collector, session: SessionDep
) -> None:
    project = await svc.get_project(session, org_id, project_id)
    evidence = await _get_evidence(session, project, evidence_id)
    # L'auteur du dépôt peut retirer sa pièce ; sinon, il faut être responsable du projet.
    if evidence.uploaded_by != member.user_id and member.role not in (
        Role.ADMIN,
        Role.PROJECT_MANAGER,
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Seul l'auteur ou un responsable peut retirer cette pièce"
        )
    _log(session, member, "evidence.deleted", "evidence", evidence.id, {"name": evidence.filename})
    await session.delete(evidence)
    await session.commit()
    storage = get_storage()
    for key in (evidence.storage_key, evidence.thumbnail_key):
        if key:
            await storage.delete(key)


@router.get("/evidence/{evidence_id}/{variant}")
async def download_evidence(
    org_id: UUID,
    project_id: UUID,
    evidence_id: UUID,
    variant: str,
    member: AnyMember,
    session: SessionDep,
) -> Response:
    if variant not in ("file", "thumbnail"):
        raise svc.not_found("Fichier")
    project = await svc.get_project(session, org_id, project_id)
    evidence = await _get_evidence(session, project, evidence_id)
    # L'original n'est pas flouté : réservé aux responsables et à l'auteur de la photo.
    if (
        variant == "file"
        and (evidence.extra or {}).get("faces")
        and member.role not in FACE_ROLES
        and evidence.uploaded_by != member.user_id
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Photo avec visages : l'original est réservé aux responsables",
        )
    key = evidence.storage_key if variant == "file" else evidence.thumbnail_key
    if not key:
        raise svc.not_found("Vignette")
    data = await get_storage().get(key)
    media_type = evidence.content_type if variant == "file" else "image/webp"
    ascii_name = evidence.filename.encode("ascii", "ignore").decode() or "piece"
    return Response(
        data,
        media_type=media_type,
        headers={
            "Content-Disposition": f'inline; filename="{ascii_name}"',
            "Cache-Control": "private, max-age=3600",
        },
    )


# --- Dépenses réelles ------------------------------------------------------------


@router.post(
    "/executions/{execution_id}/expenses",
    response_model=ExecutionExpenseOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_execution_expense(
    org_id: UUID,
    project_id: UUID,
    execution_id: UUID,
    body: ExecutionExpenseIn,
    member: Spender,
    session: SessionDep,
) -> Expense:
    project = await svc.get_project(session, org_id, project_id)
    execution = await _get_execution(session, project, execution_id)
    line = await session.scalar(
        select(BudgetLine).where(
            BudgetLine.id == body.budget_line_id, BudgetLine.project_id == project.id
        )
    )
    if line is None:
        raise svc.not_found("Ligne budgétaire")
    expense = Expense(organization_id=org_id, execution_id=execution.id, **body.model_dump())
    session.add(expense)
    await session.flush()
    _log(
        session,
        member,
        "budget.expense_recorded",
        "expense",
        expense.id,
        {"label": line.label, "amount": str(expense.amount)},
    )
    await session.commit()
    await session.refresh(expense)
    return expense
