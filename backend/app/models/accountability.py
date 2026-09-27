"""Agrégation et redevabilité : rapports périodiques, plaintes et retours, leçons apprises."""

import enum
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Date, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin
from app.models.report import ReportStatus


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


# --- Rapports périodiques et bailleur ---------------------------------------------------


class PeriodicKind(enum.StrEnum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"
    DONOR = "donor"


class PeriodicReport(IdMixin, TimestampMixin, Base):
    __tablename__ = "periodic_reports"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[PeriodicKind] = mapped_column(_enum(PeriodicKind, "periodic_kind"))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[ReportStatus] = mapped_column(
        _enum(ReportStatus, "report_status"), default=ReportStatus.DRAFT
    )
    # Mêmes conventions que les rapports narratifs : sections Markdown, renvois [S1]…
    sections: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    missing_information: Mapped[list[str]] = mapped_column(JSONB, default=list)
    instructions: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(default=1)
    review_comment: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    submitted_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PeriodicReportVersion(IdMixin, TimestampMixin, Base):
    __tablename__ = "periodic_report_versions"
    __table_args__ = (UniqueConstraint("report_id", "version"),)

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    report_id: Mapped[UUID] = mapped_column(
        ForeignKey("periodic_reports.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int]
    title: Mapped[str] = mapped_column(String(300))
    sections: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    note: Mapped[str] = mapped_column(String(200), default="")
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


# --- Plaintes et retours communautaires -------------------------------------------------


class FeedbackChannel(enum.StrEnum):
    HOTLINE = "hotline"
    SUGGESTION_BOX = "suggestion_box"
    COMMUNITY_MEETING = "community_meeting"
    FIELD_VISIT = "field_visit"
    SMS = "sms"
    EMAIL = "email"
    OTHER = "other"


class FeedbackCategory(enum.StrEnum):
    INFORMATION = "information"
    SUGGESTION = "suggestion"
    APPRECIATION = "appreciation"
    COMPLAINT = "complaint"
    FRAUD = "fraud"
    SEXUAL_EXPLOITATION = "sexual_exploitation"
    SAFETY = "safety"
    OTHER = "other"


class FeedbackStatus(enum.StrEnum):
    RECEIVED = "received"
    IN_PROGRESS = "in_progress"
    RESPONDED = "responded"
    CLOSED = "closed"


class FeedbackEntry(IdMixin, TimestampMixin, Base):
    __tablename__ = "feedback_entries"
    __table_args__ = (UniqueConstraint("project_id", "reference"),)

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    reference: Mapped[str] = mapped_column(String(20))
    received_on: Mapped[date] = mapped_column(Date)
    channel: Mapped[FeedbackChannel] = mapped_column(_enum(FeedbackChannel, "feedback_channel"))
    category: Mapped[FeedbackCategory] = mapped_column(_enum(FeedbackCategory, "feedback_category"))
    # Une entrée sensible (fraude, exploitation et abus sexuels, sécurité) n'est visible que
    # des responsables, de la personne qui l'a saisie et de celle qui la traite.
    sensitive: Mapped[bool] = mapped_column(default=False)
    description: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(String(300), default="")
    activity_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("logframe_nodes.id", ondelete="SET NULL")
    )
    anonymous: Mapped[bool] = mapped_column(default=False)
    contact: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[FeedbackStatus] = mapped_column(
        _enum(FeedbackStatus, "feedback_status"), default=FeedbackStatus.RECEIVED
    )
    assigned_to: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    response: Mapped[str] = mapped_column(Text, default="")
    responded_on: Mapped[date | None] = mapped_column(Date)
    closed_on: Mapped[date | None] = mapped_column(Date)
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    client_uuid: Mapped[UUID | None] = mapped_column(unique=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# --- Leçons apprises ----------------------------------------------------------------------


class Lesson(IdMixin, TimestampMixin, Base):
    __tablename__ = "lessons_learned"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    recommendation: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    activity_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("logframe_nodes.id", ondelete="SET NULL")
    )
    source_report_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("narrative_reports.id", ondelete="SET NULL")
    )
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
