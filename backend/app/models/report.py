"""Rapport narratif d'une exécution d'activité, rédigé à partir des preuves du terrain."""

import enum
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin


class ReportStatus(enum.StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"


class NarrativeReport(IdMixin, TimestampMixin, Base):
    __tablename__ = "narrative_reports"
    __table_args__ = (UniqueConstraint("execution_id"),)

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("activity_executions.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[ReportStatus] = mapped_column(
        Enum(ReportStatus, name="report_status", values_callable=lambda e: [m.value for m in e]),
        default=ReportStatus.DRAFT,
    )
    # Liste ordonnée de {"key", "title", "content"} en Markdown simple ; les passages
    # s'appuient sur les sources par des renvois [S1], [S2]…
    sections: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    # Sources disponibles au moment de la rédaction : {"ref", "label", "evidence_id"}.
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    missing_information: Mapped[list[str]] = mapped_column(JSONB, default=list)
    # Contributions aux indicateurs proposées par l'IA, à appliquer par un humain.
    indicator_suggestions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    version: Mapped[int] = mapped_column(default=1)
    review_comment: Mapped[str] = mapped_column(Text, default="")
    template_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("document_templates.id", ondelete="SET NULL")
    )
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    submitted_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ReportVersion(IdMixin, TimestampMixin, Base):
    __tablename__ = "report_versions"
    __table_args__ = (UniqueConstraint("report_id", "version"),)

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    report_id: Mapped[UUID] = mapped_column(
        ForeignKey("narrative_reports.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int]
    title: Mapped[str] = mapped_column(String(300))
    sections: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    note: Mapped[str] = mapped_column(String(200), default="")
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
