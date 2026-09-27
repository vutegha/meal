"""Termes de référence (TdR) d'une activité, avec leurs versions et leur circuit de validation."""

import enum
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin


class TorStatus(enum.StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"


class TermsOfReference(IdMixin, TimestampMixin, Base):
    __tablename__ = "terms_of_reference"
    # Un TdR par activité : on le révise au lieu d'en créer un second.
    __table_args__ = (UniqueConstraint("activity_id"),)

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    activity_id: Mapped[UUID] = mapped_column(ForeignKey("logframe_nodes.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[TorStatus] = mapped_column(
        Enum(TorStatus, name="tor_status", values_callable=lambda e: [m.value for m in e]),
        default=TorStatus.DRAFT,
    )
    # Liste ordonnée de {"key", "title", "content"} ; content est du Markdown simple.
    sections: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    missing_information: Mapped[list[str]] = mapped_column(JSONB, default=list)
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


class TorVersion(IdMixin, TimestampMixin, Base):
    """Instantané d'un TdR à chaque modification, pour l'historique."""

    __tablename__ = "tor_versions"
    __table_args__ = (UniqueConstraint("tor_id", "version"),)

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    tor_id: Mapped[UUID] = mapped_column(
        ForeignKey("terms_of_reference.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int]
    title: Mapped[str] = mapped_column(String(300))
    sections: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    note: Mapped[str] = mapped_column(String(200), default="")
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
