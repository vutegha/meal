"""Durées de conservation : effacement automatique des données personnelles devenues inutiles.

Lancé chaque nuit par le worker (app/workers/settings.py) ou à la main :
`uv run python -m app.scripts.purge`.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AuditLog,
    FeedbackEntry,
    FeedbackStatus,
    Organization,
    PasswordReset,
    SmsMessage,
    UserSession,
)

# SMS qu'aucun projet n'a reconnus : gardés le temps d'un éventuel rattachement manuel.
UNMATCHED_SMS_DAYS = 30
# Sessions et liens de réinitialisation expirés ou utilisés.
CREDENTIALS_DAYS = 30
# Traces de consultation (qui a vu quoi) : un an.
ACCESS_LOG_DAYS = 365
ACCESS_ACTIONS = (
    "feedback.viewed",
    "feedback.messages_viewed",
    "evidence.original_viewed",
    "form.exported",
)
ERASED = "[Contenu effacé : données personnelles]"


async def anonymize_feedback(session: AsyncSession, entries: list[FeedbackEntry]) -> None:
    """Efface le contenu personnel d'un retour et ses échanges SMS ; garde catégorie, statut
    et dates pour les statistiques."""
    if not entries:
        return
    now = datetime.now(UTC)
    for entry in entries:
        entry.description = ERASED
        entry.contact = ""
        entry.response = ""
        entry.location = ""
        entry.anonymized_at = now
    await session.execute(
        delete(SmsMessage).where(SmsMessage.feedback_id.in_([e.id for e in entries]))
    )


def _months_ago(today: date, months: int) -> date:
    year, month = divmod(today.year * 12 + today.month - 1 - months, 12)
    return date(year, month + 1, min(today.day, 28))


async def purge(session: AsyncSession, today: date | None = None) -> dict[str, Any]:
    """Applique toutes les durées de conservation ; renvoie le décompte par catégorie."""
    today = today or date.today()
    now = datetime.now(UTC)
    counts: dict[str, Any] = {}

    result = await session.execute(
        delete(SmsMessage).where(
            SmsMessage.organization_id.is_(None),
            SmsMessage.created_at < now - timedelta(days=UNMATCHED_SMS_DAYS),
        )
    )
    counts["unmatched_sms"] = result.rowcount  # type: ignore[attr-defined]

    anonymized: dict[str, int] = {}
    for org_id, months in (
        await session.execute(
            select(Organization.id, Organization.feedback_retention_months).where(
                Organization.feedback_retention_months > 0
            )
        )
    ).all():
        entries = list(
            await session.scalars(
                select(FeedbackEntry).where(
                    FeedbackEntry.organization_id == org_id,
                    FeedbackEntry.status == FeedbackStatus.CLOSED,
                    FeedbackEntry.anonymized_at.is_(None),
                    FeedbackEntry.closed_on < _months_ago(today, months),
                )
            )
        )
        await anonymize_feedback(session, entries)
        if entries:
            anonymized[str(org_id)] = len(entries)
            _record(session, org_id, len(entries), months)
    counts["feedback"] = anonymized

    stale = now - timedelta(days=CREDENTIALS_DAYS)
    result = await session.execute(
        delete(UserSession).where(
            or_(UserSession.expires_at < stale, UserSession.revoked_at < stale)
        )
    )
    counts["sessions"] = result.rowcount  # type: ignore[attr-defined]
    result = await session.execute(
        delete(PasswordReset).where(
            or_(PasswordReset.expires_at < stale, PasswordReset.used_at < stale)
        )
    )
    counts["password_resets"] = result.rowcount  # type: ignore[attr-defined]

    result = await session.execute(
        delete(AuditLog).where(
            AuditLog.action.in_(ACCESS_ACTIONS),
            AuditLog.created_at < now - timedelta(days=ACCESS_LOG_DAYS),
        )
    )
    counts["access_logs"] = result.rowcount  # type: ignore[attr-defined]
    return counts


def _record(session: AsyncSession, org_id: UUID, count: int, months: int) -> None:
    session.add(
        AuditLog(
            organization_id=org_id,
            actor_id=None,
            action="feedback.anonymized",
            entity_type="organization",
            entity_id=org_id,
            data={"count": count, "reason": f"clôturés depuis plus de {months} mois"},
        )
    )
