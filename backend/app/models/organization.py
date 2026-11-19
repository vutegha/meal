import enum
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint, false, func, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.billing import Subscription


class Role(enum.StrEnum):
    ADMIN = "admin"
    PROJECT_MANAGER = "project_manager"
    MEAL_OFFICER = "meal_officer"
    FIELD_AGENT = "field_agent"
    FINANCE = "finance"
    VIEWER = "viewer"


class Organization(IdMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    default_language: Mapped[str] = mapped_column(String(8), default="fr")
    # Protection des données (page Données personnelles de l'espace).
    # Désactivée : aucun texte de l'espace n'est envoyé aux fournisseurs d'IA.
    ai_enabled: Mapped[bool] = mapped_column(default=True, server_default=true())
    # Retours clôturés depuis plus de N mois : contact, description et SMS effacés (0 = jamais).
    feedback_retention_months: Mapped[int] = mapped_column(default=36, server_default="36")
    # Accusé de réception envoyé à qui écrit par SMS ou WhatsApp, avec la notice d'information.
    sms_acknowledgement: Mapped[bool] = mapped_column(default=True, server_default=true())
    # Personne ou service à contacter pour exercer ses droits (repris dans l'accusé).
    privacy_contact: Mapped[str] = mapped_column(String(200), default="", server_default="")

    memberships: Mapped[list["Membership"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    # Chargé avec l'organisation : le type de compte et les fonctions ouvertes en dépendent.
    subscription: Mapped["Subscription | None"] = relationship(
        lazy="selectin", passive_deletes=True
    )


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True)
    # Équipe qui exploite la plateforme : gère les abonnements de tous les espaces (/admin).
    is_platform_admin: Mapped[bool] = mapped_column(default=False, server_default=false())
    # Mot de passe fixé par un administrateur : à changer à la première connexion.
    must_change_password: Mapped[bool] = mapped_column(default=False, server_default=false())
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Double authentification (TOTP) : secret chiffré (core/crypto.py), actif une fois confirmé.
    totp_secret: Mapped[str | None] = mapped_column(String(255))
    totp_enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    memberships: Mapped[list["Membership"]] = relationship(back_populates="user")


class UserSession(IdMixin, TimestampMixin, Base):
    """Session ouverte par une connexion, révocable (déconnexion, mot de passe changé).

    Le jeton de rafraîchissement porte l'identifiant de la session et sa génération : chaque
    rafraîchissement passe à la génération suivante. Rejouer un jeton déjà remplacé (vol
    probable) révoque la session.
    """

    __tablename__ = "user_sessions"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    generation: Mapped[int] = mapped_column(default=0)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str] = mapped_column(String(200), default="")


class PasswordReset(IdMixin, TimestampMixin, Base):
    """Lien de réinitialisation à usage unique ; seule l'empreinte du jeton est gardée."""

    __tablename__ = "password_resets"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Membership(IdMixin, TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("organization_id", "user_id"),)

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[Role] = mapped_column(
        Enum(Role, name="role", values_callable=lambda e: [m.value for m in e])
    )

    organization: Mapped[Organization] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")


class AuditLog(IdMixin, Base):
    __tablename__ = "audit_logs"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[UUID | None]
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
