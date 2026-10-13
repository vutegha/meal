from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models import AccountType
from app.schemas.billing import Cycle

Status = Literal["trialing", "active", "canceled", "expired"]


class AdminSubscriptionRow(BaseModel):
    organization_id: UUID
    organization_name: str
    organization_created_at: datetime
    # Premier administrateur de l'espace : la personne à contacter.
    contact_email: str | None
    contact_name: str | None
    plan: str
    account_type: AccountType
    cycle: Cycle
    status: Status
    trial_ends_at: datetime | None
    current_period_end: datetime | None
    cancel_at_period_end: bool
    credits: int
    members: int
    projects: int
    credits_used_this_month: int
    last_payment_at: datetime | None
    total_paid: Decimal


class AdminSummary(BaseModel):
    organizations: int
    by_status: dict[str, int]
    by_plan: dict[str, int]
    # Revenu mensuel récurrent : abonnements actifs, l'annuel compté pour un douzième.
    monthly_recurring: Decimal
    revenue_last_30_days: Decimal
    currency: str


class AdminSubscriptions(BaseModel):
    summary: AdminSummary
    items: list[AdminSubscriptionRow]


class AdminSubscriptionUpdate(BaseModel):
    plan: str | None = None
    cycle: Cycle | None = None
    # Statut enregistré : « résilié » et « expiré » découlent des dates et du renouvellement.
    status: Literal["trialing", "active"] | None = None
    trial_ends_at: datetime | None = None
    current_period_end: datetime | None = None
    # Prolonge l'essai ou la période en cours de N jours (à partir d'aujourd'hui si échue).
    extend_days: int | None = Field(default=None, ge=1, le=3660)
    # Crédits ajoutés (ou retirés si négatif) au solde des formules à l'usage.
    add_credits: int | None = Field(default=None, ge=-100_000, le=100_000)
    cancel_at_period_end: bool | None = None
    note: str = Field(default="", max_length=500)
