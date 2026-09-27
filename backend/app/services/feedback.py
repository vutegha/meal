"""Registre des plaintes et retours : visibilité, délais de réponse, statistiques."""

from collections import Counter
from datetime import date, timedelta

from app.models import FeedbackCategory, FeedbackEntry, FeedbackStatus, Membership, Role
from app.schemas.accountability import FeedbackOut, FeedbackStats

# Catégories traitées de façon confidentielle par défaut.
SENSITIVE_CATEGORIES = {
    FeedbackCategory.FRAUD,
    FeedbackCategory.SEXUAL_EXPLOITATION,
    FeedbackCategory.SAFETY,
}
# Délai de réponse attendu, en jours à compter de la réception.
RESPONSE_DAYS = 14
SENSITIVE_RESPONSE_DAYS = 3
ANSWERED = {FeedbackStatus.RESPONDED, FeedbackStatus.CLOSED}
MANAGERS = {Role.ADMIN, Role.PROJECT_MANAGER}


def involved(member: Membership, entry: FeedbackEntry) -> bool:
    return member.user_id in (entry.created_by, entry.assigned_to)


def can_see(member: Membership, entry: FeedbackEntry) -> bool:
    return not entry.sensitive or member.role in MANAGERS or involved(member, entry)


def can_handle(member: Membership, entry: FeedbackEntry) -> bool:
    """Qualifier, attribuer et répondre : responsables, chargé MEAL, personne attribuée."""
    if entry.sensitive:
        return member.role in MANAGERS or member.user_id == entry.assigned_to
    return member.role in (*MANAGERS, Role.MEAL_OFFICER) or member.user_id == entry.assigned_to


def due_on(entry: FeedbackEntry) -> date:
    days = SENSITIVE_RESPONSE_DAYS if entry.sensitive else RESPONSE_DAYS
    return entry.received_on + timedelta(days=days)


def out(member: Membership, entry: FeedbackEntry, today: date | None = None) -> FeedbackOut:
    today = today or date.today()
    answered = entry.status in ANSWERED
    show_contact = member.role in (*MANAGERS, Role.MEAL_OFFICER) or involved(member, entry)
    data = {k: getattr(entry, k) for k in FeedbackOut.model_fields if hasattr(entry, k)}
    return FeedbackOut.model_validate(
        {
            **data,
            "contact": entry.contact if show_contact and not entry.anonymous else "",
            "due_on": due_on(entry),
            "overdue": not answered and today > due_on(entry),
            "response_days": (entry.responded_on - entry.received_on).days
            if entry.responded_on
            else None,
        }
    )


def stats(entries: list[FeedbackEntry], hidden: int, today: date | None = None) -> FeedbackStats:
    today = today or date.today()
    answered = [e for e in entries if e.status in ANSWERED]
    delays = [(e.responded_on - e.received_on).days for e in answered if e.responded_on]
    return FeedbackStats(
        total=len(entries),
        open=len(entries) - len(answered),
        overdue=sum(1 for e in entries if e.status not in ANSWERED and today > due_on(e)),
        response_rate=len(answered) / len(entries) if entries else None,
        average_response_days=round(sum(delays) / len(delays), 1) if delays else None,
        by_status=dict(Counter(e.status.value for e in entries)),
        by_category=dict(Counter(e.category.value for e in entries)),
        by_channel=dict(Counter(e.channel.value for e in entries)),
        hidden_sensitive=hidden,
    )
