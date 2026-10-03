"""Redevabilité et apprentissage : registre des plaintes et retours, leçons apprises."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import Select, func, or_, select

from app.api.deps import AnyMember, SessionDep
from app.api.projects import Collector, Planner, ProjectAdmin, _flush, _log
from app.core.config import get_settings
from app.llm.client import LLMError
from app.llm.prompts import feedback_classification as classify_prompt
from app.models import (
    FeedbackCategory,
    FeedbackEntry,
    FeedbackStatus,
    Lesson,
    Membership,
    NarrativeReport,
    Project,
)
from app.schemas.accountability import (
    FeedbackClassifyIn,
    FeedbackIn,
    FeedbackOut,
    FeedbackStats,
    FeedbackSuggestion,
    FeedbackUpdate,
    LessonIn,
    LessonOut,
    LessonUpdate,
)
from app.services import feedback as fb
from app.services import projects as svc
from app.services.ai import call_structured

router = APIRouter(prefix="/orgs/{org_id}", tags=["redevabilité"])
PROJECT = "/projects/{project_id}"


# --- Plaintes et retours ------------------------------------------------------------------


async def _get_feedback(
    session: SessionDep, project: Project, member: Membership, feedback_id: UUID
) -> FeedbackEntry:
    entry = await session.scalar(
        select(FeedbackEntry).where(
            FeedbackEntry.id == feedback_id, FeedbackEntry.project_id == project.id
        )
    )
    # Une entrée sensible n'existe pas pour qui n'a pas à la voir.
    if entry is None or not fb.can_see(member, entry):
        raise svc.not_found("Retour")
    return entry


async def _check_activity(session: SessionDep, project: Project, activity_id: UUID | None) -> None:
    if activity_id:
        await svc.get_node(session, project, activity_id)


async def _check_member(session: SessionDep, org_id: UUID, user_id: UUID | None) -> None:
    if user_id and not await session.scalar(
        select(Membership.id).where(
            Membership.organization_id == org_id, Membership.user_id == user_id
        )
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Cette personne n'est pas membre"
        )


@router.get(f"{PROJECT}/feedback", response_model=list[FeedbackOut])
async def list_feedback(
    org_id: UUID,
    project_id: UUID,
    member: AnyMember,
    session: SessionDep,
    status_filter: Annotated[FeedbackStatus | None, Query(alias="status")] = None,
    category: FeedbackCategory | None = None,
) -> list[FeedbackOut]:
    project = await svc.get_project(session, org_id, project_id)
    query = select(FeedbackEntry).where(FeedbackEntry.project_id == project.id)
    if status_filter:
        query = query.where(FeedbackEntry.status == status_filter)
    if category:
        query = query.where(FeedbackEntry.category == category)
    rows = await session.scalars(
        query.order_by(FeedbackEntry.received_on.desc(), FeedbackEntry.reference.desc())
    )
    return [fb.out(member, e) for e in rows if fb.can_see(member, e)]


@router.get(f"{PROJECT}/feedback/stats", response_model=FeedbackStats)
async def feedback_stats(
    org_id: UUID, project_id: UUID, member: AnyMember, session: SessionDep
) -> FeedbackStats:
    project = await svc.get_project(session, org_id, project_id)
    rows = list(
        await session.scalars(select(FeedbackEntry).where(FeedbackEntry.project_id == project.id))
    )
    # Les chiffres couvrent tout le registre ; seul le détail des entrées sensibles est masqué.
    return fb.stats(rows, hidden=sum(1 for e in rows if not fb.can_see(member, e)))


@router.post(f"{PROJECT}/feedback", response_model=FeedbackOut, status_code=201)
async def create_feedback(
    org_id: UUID,
    project_id: UUID,
    body: FeedbackIn,
    member: Collector,
    session: SessionDep,
    response: Response,
) -> FeedbackOut:
    project = await svc.get_project(session, org_id, project_id)
    if body.client_uuid:
        existing = await session.scalar(
            select(FeedbackEntry).where(
                FeedbackEntry.client_uuid == body.client_uuid,
                FeedbackEntry.project_id == project.id,
            )
        )
        if existing is not None:
            # Renvoi d'une saisie hors ligne : seul qui peut voir l'entrée la récupère.
            if not fb.can_see(member, existing):
                raise HTTPException(status.HTTP_409_CONFLICT, "Identifiant de saisie déjà utilisé")
            response.status_code = status.HTTP_200_OK
            return fb.out(member, existing)
    await _check_activity(session, project, body.activity_id)
    count = await session.scalar(select(func.count()).where(FeedbackEntry.project_id == project.id))
    data = body.model_dump()
    # Une catégorie sensible est toujours confidentielle, quoi que demande le client.
    data["sensitive"] = bool(data["sensitive"]) or body.category in fb.SENSITIVE_CATEGORIES
    if body.anonymous:
        data["contact"] = ""
    entry = FeedbackEntry(
        **data,
        organization_id=org_id,
        project_id=project.id,
        reference=f"RET-{(count or 0) + 1:04d}",
        created_by=member.user_id,
    )
    session.add(entry)
    await _flush(session, "Référence déjà utilisée, réessayez")
    # Pas de détail dans le journal : une plainte peut contenir des informations personnelles.
    _log(session, member, "feedback.recorded", "feedback", entry.id, {"reference": entry.reference})
    await session.commit()
    await session.refresh(entry)
    return fb.out(member, entry)


@router.post(f"{PROJECT}/feedback/classify", response_model=FeedbackSuggestion)
async def classify_feedback(
    org_id: UUID, project_id: UUID, body: FeedbackClassifyIn, member: Collector, session: SessionDep
) -> FeedbackSuggestion:
    """Propose un type, la sensibilité et l'urgence d'un retour avant son enregistrement.

    Seul le texte du retour est envoyé au modèle, jamais le contact de la personne.
    """
    project = await svc.get_project(session, org_id, project_id)
    try:
        result = await call_structured(
            session,
            organization_id=org_id,
            project_id=project.id,
            purpose="feedback_classification",
            prompt_version=classify_prompt.VERSION,
            model=get_settings().llm_model_light,
            system=classify_prompt.SYSTEM,
            content=classify_prompt.build_content(body.description, body.channel),
            output_type=FeedbackSuggestion,
            effort=None,
        )
    except LLMError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    suggestion = result.output
    # Une catégorie sensible l'est toujours, quoi qu'en dise le modèle.
    if suggestion.category in fb.SENSITIVE_CATEGORIES:
        suggestion.sensitive = True
        suggestion.urgency = "high"
    return suggestion


@router.patch(f"{PROJECT}/feedback/{{feedback_id}}", response_model=FeedbackOut)
async def update_feedback(
    org_id: UUID,
    project_id: UUID,
    feedback_id: UUID,
    body: FeedbackUpdate,
    member: AnyMember,
    session: SessionDep,
) -> FeedbackOut:
    project = await svc.get_project(session, org_id, project_id)
    entry = await _get_feedback(session, project, member, feedback_id)
    if not fb.can_handle(member, entry):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Vous ne traitez pas ce retour")
    changes = body.model_dump(exclude_unset=True)
    if "activity_id" in changes:
        await _check_activity(session, project, changes["activity_id"])
    if "assigned_to" in changes:
        await _check_member(session, org_id, changes["assigned_to"])
    if "category" in changes and "sensitive" not in changes:
        changes["sensitive"] = entry.sensitive or changes["category"] in fb.SENSITIVE_CATEGORIES
    if changes.get("sensitive") is False and entry.sensitive and member.role not in fb.MANAGERS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé au chef de projet")
    for key, value in changes.items():
        if key == "sensitive" and value is None:
            continue
        setattr(entry, key, value)
    if entry.category in fb.SENSITIVE_CATEGORIES:
        entry.sensitive = True
    if entry.anonymous:
        entry.contact = ""

    if entry.status in fb.ANSWERED:
        if not entry.response.strip():
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Indiquez la réponse apportée avant de clore ce retour",
            )
        entry.responded_on = entry.responded_on or date.today()
    if entry.status == FeedbackStatus.CLOSED:
        entry.closed_on = entry.closed_on or date.today()
    else:
        entry.closed_on = None
    if entry.responded_on and entry.responded_on < entry.received_on:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "La réponse précède la réception"
        )
    _log(
        session,
        member,
        "feedback.updated",
        "feedback",
        entry.id,
        {"reference": entry.reference, "status": entry.status.value},
    )
    await session.commit()
    await session.refresh(entry)
    return fb.out(member, entry)


@router.delete(f"{PROJECT}/feedback/{{feedback_id}}", status_code=204)
async def delete_feedback(
    org_id: UUID, project_id: UUID, feedback_id: UUID, member: ProjectAdmin, session: SessionDep
) -> None:
    project = await svc.get_project(session, org_id, project_id)
    entry = await _get_feedback(session, project, member, feedback_id)
    _log(session, member, "feedback.deleted", "feedback", entry.id, {"reference": entry.reference})
    await session.delete(entry)
    await session.commit()


# --- Leçons apprises -----------------------------------------------------------------------


def _lesson_query(org_id: UUID, q: str, tag: str) -> Select[Lesson, str]:
    query = (
        select(Lesson, Project.code)
        .join(Project, Project.id == Lesson.project_id)
        .where(Lesson.organization_id == org_id)
    )
    if q.strip():
        pattern = f"%{q.strip()}%"
        query = query.where(
            or_(
                Lesson.title.ilike(pattern),
                Lesson.description.ilike(pattern),
                Lesson.recommendation.ilike(pattern),
            )
        )
    if tag.strip():
        query = query.where(Lesson.tags.contains([tag.strip().lower()]))
    return query.order_by(Lesson.created_at.desc())


def _lesson_out(lesson: Lesson, code: str) -> LessonOut:
    return LessonOut.model_validate(lesson).model_copy(update={"project_code": code})


@router.get("/lessons", response_model=list[LessonOut])
async def list_org_lessons(
    org_id: UUID, _: AnyMember, session: SessionDep, q: str = "", tag: str = ""
) -> list[LessonOut]:
    """Toutes les leçons de l'organisation, pour apprendre d'un projet à l'autre."""
    rows = await session.execute(_lesson_query(org_id, q, tag))
    return [_lesson_out(lesson, code) for lesson, code in rows]


@router.get(f"{PROJECT}/lessons", response_model=list[LessonOut])
async def list_lessons(
    org_id: UUID,
    project_id: UUID,
    _: AnyMember,
    session: SessionDep,
    q: str = "",
    tag: str = "",
) -> list[LessonOut]:
    project = await svc.get_project(session, org_id, project_id)
    rows = await session.execute(
        _lesson_query(org_id, q, tag).where(Lesson.project_id == project.id)
    )
    return [_lesson_out(lesson, code) for lesson, code in rows]


async def _get_lesson(session: SessionDep, project: Project, lesson_id: UUID) -> Lesson:
    lesson = await session.scalar(
        select(Lesson).where(Lesson.id == lesson_id, Lesson.project_id == project.id)
    )
    if lesson is None:
        raise svc.not_found("Leçon")
    return lesson


@router.post(f"{PROJECT}/lessons", response_model=LessonOut, status_code=201)
async def create_lesson(
    org_id: UUID, project_id: UUID, body: LessonIn, member: Planner, session: SessionDep
) -> LessonOut:
    project = await svc.get_project(session, org_id, project_id)
    await _check_activity(session, project, body.activity_id)
    if body.source_report_id and not await session.scalar(
        select(NarrativeReport.id).where(
            NarrativeReport.id == body.source_report_id, NarrativeReport.project_id == project.id
        )
    ):
        raise svc.not_found("Rapport")
    lesson = Lesson(
        **body.model_dump(),
        organization_id=org_id,
        project_id=project.id,
        created_by=member.user_id,
    )
    session.add(lesson)
    await session.flush()
    _log(session, member, "lesson.created", "lesson", lesson.id, {"title": lesson.title})
    await session.commit()
    await session.refresh(lesson)
    return _lesson_out(lesson, project.code)


@router.patch(f"{PROJECT}/lessons/{{lesson_id}}", response_model=LessonOut)
async def update_lesson(
    org_id: UUID,
    project_id: UUID,
    lesson_id: UUID,
    body: LessonUpdate,
    member: Planner,
    session: SessionDep,
) -> LessonOut:
    project = await svc.get_project(session, org_id, project_id)
    lesson = await _get_lesson(session, project, lesson_id)
    changes = body.model_dump(exclude_unset=True)
    if "activity_id" in changes:
        await _check_activity(session, project, changes["activity_id"])
    for key, value in changes.items():
        if value is not None or key == "activity_id":
            setattr(lesson, key, value)
    _log(session, member, "lesson.updated", "lesson", lesson.id, {"title": lesson.title})
    await session.commit()
    await session.refresh(lesson)
    return _lesson_out(lesson, project.code)


@router.delete(f"{PROJECT}/lessons/{{lesson_id}}", status_code=204)
async def delete_lesson(
    org_id: UUID, project_id: UUID, lesson_id: UUID, member: Planner, session: SessionDep
) -> None:
    project = await svc.get_project(session, org_id, project_id)
    lesson = await _get_lesson(session, project, lesson_id)
    _log(session, member, "lesson.deleted", "lesson", lesson.id, {"title": lesson.title})
    await session.delete(lesson)
    await session.commit()
