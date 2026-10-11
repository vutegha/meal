"""Abonnement de chaque espace (compte individuel ou organisation) et paiements reçus.

La formule (`plan`) détermine le type de compte, les limites et les fonctions ouvertes : voir
`app/services/billing.py`. Les paiements passent pour l'instant par un prestataire simulé.
"""

import enum
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin


class AccountType(enum.StrEnum):
    INDIVIDUAL = "individual"
    ORGANIZATION = "organization"


# Cycles de facturation : mensuel, annuel, ou à l'usage (crédits achetés à l'unité).
CYCLES = ("monthly", "annual", "usage")


class Subscription(IdMixin, TimestampMixin, Base):
    """Une ligne par espace. Hors RLS, comme `memberships` : `/auth/me` la lit pour chaque
    organisation de l'utilisateur sans en sélectionner une."""

    __tablename__ = "subscriptions"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), unique=True
    )
    plan: Mapped[str] = mapped_column(String(40))
    cycle: Mapped[str] = mapped_column(String(20))
    # trialing, active, canceled ; « expired » est calculé à la lecture (voir services/billing).
    status: Mapped[str] = mapped_column(String(20))
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Crédits restants des formules à l'usage : une génération IA consomme un crédit.
    credits: Mapped[int] = mapped_column(default=0)
    cancel_at_period_end: Mapped[bool] = mapped_column(default=False)


class Payment(IdMixin, TimestampMixin, Base):
    __tablename__ = "payments"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    plan: Mapped[str] = mapped_column(String(40))
    cycle: Mapped[str] = mapped_column(String(20))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3))
    credits: Mapped[int] = mapped_column(default=0)
    description: Mapped[str] = mapped_column(String(300))
    provider: Mapped[str] = mapped_column(String(40))
    reference: Mapped[str] = mapped_column(String(80))
    paid_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
