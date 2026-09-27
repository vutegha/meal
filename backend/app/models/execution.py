"""Exécution des activités sur le terrain et preuves collectées."""

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, IdMixin, TimestampMixin


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class ExecutionStatus(enum.StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class EvidenceKind(enum.StrEnum):
    REPORT = "report"
    MINUTES = "minutes"
    ATTENDANCE = "attendance"
    PHOTO = "photo"
    OTHER = "other"


class ActivityExecution(IdMixin, TimestampMixin, Base):
    __tablename__ = "activity_executions"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    activity_id: Mapped[UUID] = mapped_column(
        ForeignKey("logframe_nodes.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(300), default="")
    start_date: Mapped[date]
    end_date: Mapped[date | None]
    location: Mapped[str] = mapped_column(String(300), default="")
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    # Participants désagrégés : women, men, girls, boys, with_disability.
    participants: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict)
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[ExecutionStatus] = mapped_column(
        _enum(ExecutionStatus, "execution_status"), default=ExecutionStatus.IN_PROGRESS
    )
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # Identifiant créé par le client hors ligne : renvoyer deux fois la même saisie ne la
    # duplique pas.
    client_uuid: Mapped[UUID | None] = mapped_column(unique=True)

    evidence: Mapped[list["Evidence"]] = relationship(
        back_populates="execution", cascade="all, delete-orphan", order_by="Evidence.created_at"
    )


class Evidence(IdMixin, TimestampMixin, Base):
    __tablename__ = "evidence"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("activity_executions.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[EvidenceKind] = mapped_column(_enum(EvidenceKind, "evidence_kind"))
    filename: Mapped[str] = mapped_column(String(300))
    content_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(300))
    thumbnail_key: Mapped[str] = mapped_column(String(300), default="")
    caption: Mapped[str] = mapped_column(Text, default="")
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    # Photos de personnes : sans consentement, la photo reste dans le dossier mais n'est pas
    # reprise dans les rapports.
    consent_given: Mapped[bool] = mapped_column(default=False)
    # Texte extrait des documents (comptes rendus, rapports) pour le rapport narratif.
    text: Mapped[str] = mapped_column(Text, default="")
    page_count: Mapped[int] = mapped_column(default=0)
    uploaded_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    client_uuid: Mapped[UUID | None] = mapped_column(unique=True)
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    execution: Mapped[ActivityExecution] = relationship(back_populates="evidence")
