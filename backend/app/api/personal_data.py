"""Droits des personnes : retrouver, exporter et effacer les données d'une personne.

Réservé aux administrateurs de l'organisation, qui répondent aux demandes (RGPD, art. 15 à 17).
Le journal garde le nombre d'éléments trouvés ou effacés, jamais ce qui a été cherché.
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import String, cast, delete, func, or_, select

from app.api.deps import OrgAdmin, SessionDep
from app.models import (
    CollectionForm,
    Evidence,
    FeedbackEntry,
    FormSubmission,
    Project,
    SmsMessage,
)
from app.schemas.personal_data import (
    ErasureIn,
    ErasureOut,
    EvidenceMatch,
    FeedbackMatch,
    PersonalDataResult,
    SubmissionMatch,
)
from app.services import audit, sms
from app.services.retention import anonymize_feedback

router = APIRouter(prefix="/orgs/{org_id}/personal-data", tags=["données personnelles"])

LIMIT = 200


def _like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _excerpt(text: str, needle: str, width: int = 80) -> str:
    index = text.lower().find(needle.lower())
    if index < 0:
        return ""
    start = max(0, index - width)
    return ("…" if start else "") + text[start : index + len(needle) + width].strip() + "…"


@router.get("", response_model=PersonalDataResult)
async def search_person(
    org_id: UUID,
    admin: OrgAdmin,
    session: SessionDep,
    q: str = Query(min_length=3, max_length=200),
) -> PersonalDataResult:
    """Tout ce qui mentionne une personne : nom, numéro de téléphone ou adresse e-mail."""
    needle = q.strip()
    pattern = _like(needle)
    phone = sms.normalize_phone(needle)
    projects = {p.id: p.code for p in await session.scalars(select(Project))}

    feedback_filter = [
        FeedbackEntry.contact.ilike(pattern),
        FeedbackEntry.description.ilike(pattern),
        FeedbackEntry.response.ilike(pattern),
    ]
    if phone:
        # Un même numéro s'écrit « +243 99 000-0001 » ou « 0990000001 » : on compare les
        # 9 derniers chiffres du contact saisi.
        digits = func.regexp_replace(FeedbackEntry.contact, "[^0-9]", "", "g")
        phone_ids = select(SmsMessage.feedback_id).where(SmsMessage.phone == phone)
        feedback_filter += [digits.like(f"%{phone[-9:]}"), FeedbackEntry.id.in_(phone_ids)]
    entries = list(
        await session.scalars(
            select(FeedbackEntry)
            .where(or_(*feedback_filter))
            .order_by(FeedbackEntry.received_on.desc())
            .limit(LIMIT)
        )
    )
    messages: dict[UUID, list[dict[str, Any]]] = {}
    if entries:
        for m in await session.scalars(
            select(SmsMessage)
            .where(SmsMessage.feedback_id.in_([e.id for e in entries]))
            .order_by(SmsMessage.created_at)
        ):
            assert m.feedback_id is not None
            messages.setdefault(m.feedback_id, []).append(
                {
                    "date": m.created_at.isoformat(),
                    "direction": m.direction.value,
                    "channel": m.channel,
                    "phone": m.phone,
                    "body": m.body,
                }
            )

    submissions = (
        await session.execute(
            select(FormSubmission, CollectionForm.title)
            .join(CollectionForm, CollectionForm.id == FormSubmission.form_id)
            .where(
                or_(
                    cast(FormSubmission.answers, String).ilike(pattern),
                    FormSubmission.location.ilike(pattern),
                )
            )
            .order_by(FormSubmission.collected_at.desc())
            .limit(LIMIT)
        )
    ).all()

    evidence = list(
        await session.scalars(
            select(Evidence)
            .where(or_(Evidence.caption.ilike(pattern), Evidence.text.ilike(pattern)))
            .limit(LIMIT)
        )
    )

    result = PersonalDataResult(
        query=needle,
        feedback=[
            FeedbackMatch(
                id=e.id,
                project_code=projects.get(e.project_id, ""),
                reference=e.reference,
                received_on=e.received_on,
                category=e.category.value,
                status=e.status.value,
                sensitive=e.sensitive,
                contact=e.contact,
                description=e.description,
                response=e.response,
                anonymized=e.anonymized_at is not None,
                messages=messages.get(e.id, []),
            )
            for e in entries
        ],
        submissions=[
            SubmissionMatch(
                id=s.id,
                project_code=projects.get(s.project_id, ""),
                form_title=title,
                collected_at=s.collected_at,
                location=s.location,
                answers=s.answers,
            )
            for s, title in submissions
        ],
        evidence=[
            EvidenceMatch(
                id=e.id,
                project_code=projects.get(e.project_id, ""),
                filename=e.filename,
                kind=e.kind.value,
                caption=e.caption,
                excerpt=_excerpt(e.text, needle),
            )
            for e in evidence
        ],
    )
    audit.record(
        session,
        organization_id=org_id,
        actor_id=admin.user_id,
        action="personal_data.searched",
        entity_type="organization",
        entity_id=org_id,
        data={
            "feedback": len(result.feedback),
            "submissions": len(result.submissions),
            "evidence": len(result.evidence),
        },
    )
    await session.commit()
    return result


@router.post("/erase", response_model=ErasureOut)
async def erase_person(
    org_id: UUID, body: ErasureIn, admin: OrgAdmin, session: SessionDep
) -> ErasureOut:
    """Efface le contenu des retours choisis (et leurs SMS) et supprime les réponses choisies."""
    entries = (
        list(
            await session.scalars(
                select(FeedbackEntry).where(FeedbackEntry.id.in_(body.feedback_ids))
            )
        )
        if body.feedback_ids
        else []
    )
    if len(entries) != len(set(body.feedback_ids)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Retour introuvable")
    await anonymize_feedback(session, entries)
    removed = 0
    if body.submission_ids:
        result = await session.execute(
            delete(FormSubmission).where(FormSubmission.id.in_(body.submission_ids))
        )
        removed = result.rowcount  # type: ignore[attr-defined]
    audit.record(
        session,
        organization_id=org_id,
        actor_id=admin.user_id,
        action="personal_data.erased",
        entity_type="organization",
        entity_id=org_id,
        data={
            "feedback": [e.reference for e in entries],
            "submissions": removed,
            "reason": body.reason,
        },
    )
    await session.commit()
    return ErasureOut(feedback=len(entries), submissions=removed)
