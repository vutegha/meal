"""Modèles de documents propres à chaque organisation, et au besoin à chaque bailleur."""

from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin

# Types de documents qui acceptent un modèle.
TEMPLATE_KINDS = ("tor", "report", "periodic")


class DocumentTemplate(IdMixin, TimestampMixin, Base):
    """Sections (titre et consigne de rédaction) et mise en page d'un type de document.

    Un modèle sans bailleur vaut pour toute l'organisation ; un modèle avec bailleur s'applique
    aux projets de ce bailleur et prime sur celui de l'organisation.
    """

    __tablename__ = "document_templates"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(200))
    donor: Mapped[str] = mapped_column(String(200), default="")
    is_default: Mapped[bool] = mapped_column(default=False)
    # [{"key": "contexte", "title": "Contexte", "guidance": "…"}]
    sections: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    # {"header": "…", "footer": "…", "color": "#0f5b52"}
    layout: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
