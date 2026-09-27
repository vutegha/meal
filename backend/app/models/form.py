"""Formulaires de collecte personnalisés (enquêtes, suivi post-distribution) et réponses."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin

# Brouillon (questions modifiables), publié (réponses acceptées), clos (lecture seule).
FORM_STATUSES = ("draft", "published", "closed")
FIELD_TYPES = ("text", "number", "integer", "select", "multiselect", "yesno", "date")


class CollectionForm(IdMixin, TimestampMixin, Base):
    __tablename__ = "collection_forms"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    # [{"key", "label", "type", "required", "options": [...], "hint"}]
    fields: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    activity_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("logframe_nodes.id", ondelete="SET NULL")
    )
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class FormSubmission(IdMixin, TimestampMixin, Base):
    __tablename__ = "form_submissions"
    __table_args__ = (UniqueConstraint("client_uuid"),)

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    form_id: Mapped[UUID] = mapped_column(
        ForeignKey("collection_forms.id", ondelete="CASCADE"), index=True
    )
    answers: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    location: Mapped[str] = mapped_column(String(300), default="")
    latitude: Mapped[float | None]
    longitude: Mapped[float | None]
    # Date de la collecte sur le terrain (la réponse peut être envoyée plus tard).
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    client_uuid: Mapped[UUID | None]
    submitted_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
