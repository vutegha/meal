"""Circuit de validation commun aux documents rédigés : brouillon, soumis, approuvé."""

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from fastapi import HTTPException, status

from app.models import Membership, ReportStatus, Role

VERBS = {"submit": "submitted", "approve": "approved", "return": "returned", "reopen": "reopened"}


class Reviewable(Protocol):
    status: ReportStatus
    review_comment: str
    submitted_by: UUID | None
    submitted_at: datetime | None
    approved_by: UUID | None
    approved_at: datetime | None


def _require(doc: Reviewable, expected: ReportStatus, message: str) -> None:
    if doc.status != expected:
        raise HTTPException(status.HTTP_409_CONFLICT, message)


def transition(doc: Reviewable, action: str, member: Membership, comment: str) -> str:
    """Applique l'action et renvoie le verbe pour le journal d'audit.

    submit : rédacteurs ; approve, return, reopen : chef de projet ou administrateur.
    """
    if action not in VERBS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Action introuvable")
    if action != "submit" and member.role not in (Role.ADMIN, Role.PROJECT_MANAGER):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé au chef de projet")
    comment = comment.strip()
    if action == "submit":
        _require(doc, ReportStatus.DRAFT, "Ce document a déjà été soumis")
        doc.status = ReportStatus.SUBMITTED
        doc.submitted_by, doc.submitted_at = member.user_id, datetime.now(UTC)
        doc.review_comment = ""
    elif action == "approve":
        _require(doc, ReportStatus.SUBMITTED, "Seuls les documents soumis peuvent être approuvés")
        doc.status = ReportStatus.APPROVED
        doc.approved_by, doc.approved_at = member.user_id, datetime.now(UTC)
        doc.review_comment = comment
    elif action == "return":
        _require(doc, ReportStatus.SUBMITTED, "Seuls les documents soumis peuvent être renvoyés")
        if not comment:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Expliquez ce qui doit être revu"
            )
        doc.status, doc.review_comment = ReportStatus.DRAFT, comment
    else:
        _require(doc, ReportStatus.APPROVED, "Seuls les documents approuvés peuvent être rouverts")
        doc.status = ReportStatus.DRAFT
        doc.approved_by = doc.approved_at = None
    return VERBS[action]
