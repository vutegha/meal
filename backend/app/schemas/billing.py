from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models import AccountType

Cycle = Literal["monthly", "annual", "usage"]


class PlanLimits(BaseModel):
    projects: int | None
    members: int | None
    # Crédits IA compris chaque mois (formules mensuelles et annuelles).
    monthly_credits: int


class PlanPrices(BaseModel):
    monthly: Decimal
    annual: Decimal
    credit: Decimal


class PlanOut(BaseModel):
    id: str
    account_type: AccountType
    prices: PlanPrices
    limits: PlanLimits
    features: list[str]


class Catalog(BaseModel):
    currency: str
    trial_days: int
    welcome_credits: int
    credit_packs: list[int]
    plans: list[PlanOut]


class BillingUsage(BaseModel):
    projects: int
    members: int
    credits_used_this_month: int


class SubscriptionOut(BaseModel):
    plan: str
    account_type: AccountType
    cycle: Cycle
    status: Literal["trialing", "active", "canceled", "expired"]
    trial_ends_at: datetime | None
    current_period_end: datetime | None
    credits: int
    cancel_at_period_end: bool
    limits: PlanLimits
    features: list[str]
    usage: BillingUsage


class CheckoutIn(BaseModel):
    plan: str
    cycle: Cycle
    # Nombre de crédits achetés (formules à l'usage) : l'un des packs du catalogue.
    pack: int | None = None


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan: str
    cycle: Cycle
    amount: Decimal
    currency: str
    credits: int
    description: str
    provider: str
    reference: str
    created_at: datetime


class CheckoutOut(BaseModel):
    payment: PaymentOut
    subscription: SubscriptionOut
