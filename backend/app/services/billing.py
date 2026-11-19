"""Formules, abonnements et droits de chaque espace.

Un espace est soit un **compte individuel** (une personne, sans équipe), soit une
**organisation** (membres, rôles, modèles et leçons partagés). La formule choisie fixe le type de
compte, les limites (projets, membres, budget IA) et les fonctions ouvertes. Elle se paie au mois,
à l'année, ou à l'usage : des crédits achetés à l'unité, une génération IA (extraction, TdR,
rapport) consommant un crédit.

Les tarifs sont indicatifs et se modifient ici : l'interface publique les lit depuis
`GET /api/v1/billing/plans`. Le paiement en ligne passe par un prestataire simulé (`PROVIDER`) qui
encaisse immédiatement : c'est l'unique point à remplacer pour brancher un vrai prestataire.
Un client peut aussi annoncer un virement ou un envoi mobile money : le paiement reste en attente
jusqu'à ce que l'équipe de la plateforme le confirme depuis /admin (`mark_paid`). Chaque paiement
encaissé reçoit un numéro de reçu continu (WM-2026-000042) et un reçu PDF (`services/receipts.py`).
"""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models import (
    AccountType,
    AiCall,
    Membership,
    Organization,
    Payment,
    PaymentStatus,
    Project,
    Subscription,
)
from app.models.billing import RECEIPT_SEQUENCE

CURRENCY = "USD"
TRIAL_DAYS = 14
# Crédits offerts à l'ouverture d'un espace à l'usage, pour essayer l'IA.
WELCOME_CREDITS = 5
CREDIT_PACKS = (10, 50, 200)
PROVIDER = "simulation"
# Coordonnées de paiement hors ligne tant que PAYMENT_INSTRUCTIONS n'est pas renseigné.
DEFAULT_PAYMENT_INSTRUCTIONS = (
    "Virement : banque et numéro de compte à préciser. Mobile money : numéro à préciser. "
    "Indiquez la référence du paiement dans le motif."
)


def payment_instructions() -> str:
    return get_settings().payment_instructions.strip() or DEFAULT_PAYMENT_INSTRUCTIONS


# Appels IA décomptés en crédits sur les formules à l'usage. La lecture de pages scannées, la
# classification d'un retour et la recherche sont incluses.
CREDIT_PURPOSES = frozenset(
    {"logframe_extraction", "tor_generation", "report_generation", "periodic_generation"}
)


# Fonctions ouvertes à toutes les formules.
CORE_FEATURES = (
    "projects",
    "ai_extraction",
    "tor",
    "offline_collection",
    "reports",
    "dashboard",
    "accountability",
    "exports",
)
# Ajoutées par la formule Équipe : travail à plusieurs et suivi dans la durée.
TEAM_FEATURES = (
    "forms",
    "periodic_reports",
    "team",
    "templates",
    "org_lessons",
    "audit",
)
# Ajoutées par la formule Institution : SMS et WhatsApp vers les communautés.
INSTITUTION_FEATURES = ("messaging",)
ALL_FEATURES = CORE_FEATURES + TEAM_FEATURES + INSTITUTION_FEATURES


@dataclass(frozen=True)
class Plan:
    id: str
    account_type: AccountType
    monthly: Decimal
    annual: Decimal
    credit: Decimal
    max_projects: int | None
    max_members: int | None
    # Générations IA comprises chaque mois dans les formules mensuelles et annuelles. C'est ce
    # que voient les clients ; le plafond en dollars, interne, protège des appels très coûteux.
    monthly_credits: int
    ai_monthly_budget_usd: Decimal
    features: tuple[str, ...]

    def price(self, cycle: str) -> Decimal:
        return {"monthly": self.monthly, "annual": self.annual, "usage": self.credit}[cycle]


PLANS: dict[str, Plan] = {
    plan.id: plan
    for plan in (
        Plan(
            id="solo",
            account_type=AccountType.INDIVIDUAL,
            monthly=Decimal("12"),
            annual=Decimal("120"),
            credit=Decimal("2.00"),
            max_projects=3,
            max_members=1,
            monthly_credits=20,
            ai_monthly_budget_usd=Decimal("10"),
            features=CORE_FEATURES,
        ),
        Plan(
            id="team",
            account_type=AccountType.ORGANIZATION,
            monthly=Decimal("59"),
            annual=Decimal("590"),
            credit=Decimal("1.50"),
            max_projects=15,
            max_members=15,
            monthly_credits=100,
            ai_monthly_budget_usd=Decimal("50"),
            features=CORE_FEATURES + TEAM_FEATURES,
        ),
        Plan(
            id="institution",
            account_type=AccountType.ORGANIZATION,
            monthly=Decimal("249"),
            annual=Decimal("2490"),
            credit=Decimal("1.00"),
            max_projects=None,
            max_members=None,
            monthly_credits=500,
            ai_monthly_budget_usd=Decimal("250"),
            features=ALL_FEATURES,
        ),
    )
}

DEFAULT_PLAN = {AccountType.INDIVIDUAL: "solo", AccountType.ORGANIZATION: "team"}


def payment_required(message: str) -> HTTPException:
    return HTTPException(status.HTTP_402_PAYMENT_REQUIRED, message)


def get_plan(plan_id: str) -> Plan:
    plan = PLANS.get(plan_id)
    if plan is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Formule inconnue")
    return plan


def new_subscription(organization_id: UUID, plan_id: str, cycle: str) -> Subscription:
    """Essai gratuit au mois ou à l'année ; crédits de bienvenue à l'usage."""
    get_plan(plan_id)
    if cycle == "usage":
        return Subscription(
            organization_id=organization_id,
            plan=plan_id,
            cycle=cycle,
            status="active",
            credits=WELCOME_CREDITS,
            cancel_at_period_end=False,
        )
    return Subscription(
        organization_id=organization_id,
        plan=plan_id,
        cycle=cycle,
        status="trialing",
        trial_ends_at=datetime.now(UTC) + timedelta(days=TRIAL_DAYS),
        credits=0,
        cancel_at_period_end=False,
    )


def effective_status(sub: Subscription, now: datetime | None = None) -> str:
    """trialing, active, canceled (jusqu'à la fin de la période payée) ou expired."""
    now = now or datetime.now(UTC)
    if sub.cycle == "usage" and sub.status != "trialing":
        return "active"
    end = sub.trial_ends_at if sub.status == "trialing" else sub.current_period_end
    if end is None or end <= now:
        return "expired"
    return "canceled" if sub.cancel_at_period_end else sub.status


def features_of(sub: Subscription | None) -> list[str]:
    return list(PLANS[sub.plan].features) if sub else []


def account_type_of(sub: Subscription | None) -> AccountType:
    return PLANS[sub.plan].account_type if sub else AccountType.ORGANIZATION


async def get_subscription(
    session: AsyncSession, org_id: UUID, *, for_update: bool = False
) -> Subscription:
    """`for_update` : abonnement verrouillé jusqu'à la fin de la transaction (crédits ou échéance
    modifiés), pour que deux encaissements simultanés s'additionnent au lieu de s'écraser."""
    query = select(Subscription).where(Subscription.organization_id == org_id)
    sub = await session.scalar(query.with_for_update() if for_update else query)
    if sub is None:
        # Espace créé hors des parcours d'inscription : il démarre un essai de la formule équipe.
        sub = new_subscription(org_id, DEFAULT_PLAN[AccountType.ORGANIZATION], "monthly")
        session.add(sub)
        await session.flush()
    return sub


PLAN_NAMES = {"solo": "Solo", "team": "Équipe", "institution": "Institution"}


def lowest_plan_with(feature: str) -> Plan | None:
    """La formule la moins chère qui ouvre cette fonction (les formules sont classées par prix)."""
    return next((plan for plan in PLANS.values() if feature in plan.features), None)


async def require_feature(session: AsyncSession, org_id: UUID, feature: str) -> Subscription:
    sub = await get_subscription(session, org_id)
    if feature not in PLANS[sub.plan].features:
        plan = lowest_plan_with(feature)
        name = PLAN_NAMES.get(plan.id, plan.id) if plan else "supérieure"
        raise payment_required(
            f"Cette fonction est disponible à partir de la formule {name}. "
            "Changez de formule depuis la page Abonnement."
        )
    return sub


async def require_active(session: AsyncSession, org_id: UUID) -> Subscription:
    sub = await get_subscription(session, org_id)
    if effective_status(sub) == "expired":
        raise payment_required(
            "L'abonnement de cet espace a expiré : vos données restent consultables, "
            "renouvelez-le depuis la page Abonnement pour continuer."
        )
    return sub


async def count_projects(session: AsyncSession, org_id: UUID) -> int:
    return (
        await session.scalar(
            select(func.count()).select_from(Project).where(Project.organization_id == org_id)
        )
        or 0
    )


async def count_members(session: AsyncSession, org_id: UUID) -> int:
    return (
        await session.scalar(
            select(func.count()).select_from(Membership).where(Membership.organization_id == org_id)
        )
        or 0
    )


async def ensure_can_create_project(session: AsyncSession, org_id: UUID) -> None:
    sub = await require_active(session, org_id)
    limit = PLANS[sub.plan].max_projects
    if limit is not None and await count_projects(session, org_id) >= limit:
        raise payment_required(
            f"Votre formule permet {limit} projets. Passez à une formule supérieure pour en "
            "créer davantage."
        )


async def ensure_can_add_member(session: AsyncSession, org_id: UUID) -> None:
    sub = await require_feature(session, org_id, "team")
    await require_active(session, org_id)
    limit = PLANS[sub.plan].max_members
    if limit is not None and await count_members(session, org_id) >= limit:
        raise payment_required(
            f"Votre formule permet {limit} membres. Passez à une formule supérieure pour en "
            "ajouter davantage."
        )


async def ai_cap(session: AsyncSession, org_id: UUID) -> Decimal | None:
    """Plafond mensuel de dépense IA : celui de la formule, borné par celui du serveur."""
    caps = []
    server_cap = Decimal(str(get_settings().ai_monthly_budget_usd))
    if server_cap > 0:
        caps.append(server_cap)
    sub = await session.scalar(select(Subscription).where(Subscription.organization_id == org_id))
    if sub is not None:
        caps.append(PLANS[sub.plan].ai_monthly_budget_usd)
    return min(caps) if caps else None


def month_start() -> datetime:
    return datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def credits_used_this_month(session: AsyncSession, org_id: UUID) -> int:
    """Générations IA réussies depuis le début du mois (celles qui consomment un crédit)."""
    return (
        await session.scalar(
            select(func.count())
            .select_from(AiCall)
            .where(
                AiCall.organization_id == org_id,
                AiCall.status == "ok",
                AiCall.purpose.in_(CREDIT_PURPOSES),
                AiCall.created_at >= month_start(),
            )
        )
        or 0
    )


async def ai_block_reason(session: AsyncSession, org_id: UUID, purpose: str) -> str | None:
    """Pourquoi un appel IA n'est pas permis (IA désactivée, abonnement expiré, plus de
    crédits), sinon None."""
    if (
        await session.scalar(select(Organization.ai_enabled).where(Organization.id == org_id))
        is False
    ):
        return (
            "L'IA est désactivée pour cet espace (page Données personnelles) : aucun texte "
            "n'est envoyé aux fournisseurs d'IA."
        )
    sub = await session.scalar(select(Subscription).where(Subscription.organization_id == org_id))
    if sub is None:
        return None
    if effective_status(sub) == "expired":
        return (
            "L'abonnement de cet espace a expiré : renouvelez-le depuis la page Abonnement "
            "pour utiliser l'IA."
        )
    if purpose not in CREDIT_PURPOSES:
        return None
    if sub.cycle == "usage":
        if sub.credits <= 0:
            return "Plus de crédits disponibles : achetez un pack depuis la page Abonnement."
        return None
    quota = PLANS[sub.plan].monthly_credits
    if await credits_used_this_month(session, org_id) >= quota:
        return (
            f"Les {quota} crédits IA du mois sont utilisés : ils se renouvellent le 1er du mois, "
            "ou passez à une formule supérieure depuis la page Abonnement."
        )
    return None


async def spend_credit(org_id: UUID, purpose: str) -> None:
    """Décompte un crédit après une génération réussie, dans sa propre transaction : il reste
    consommé même si la suite du traitement échoue (l'appel au modèle, lui, a eu lieu)."""
    if purpose not in CREDIT_PURPOSES:
        return
    async with SessionLocal() as session:
        await session.execute(
            update(Subscription)
            .where(
                Subscription.organization_id == org_id,
                Subscription.cycle == "usage",
                Subscription.credits > 0,
            )
            .values(credits=Subscription.credits - 1)
        )
        await session.commit()


def period(cycle: str) -> timedelta:
    return timedelta(days=365) if cycle == "annual" else timedelta(days=30)


def _plan_and_amount(plan: Plan, cycle: str, pack: int | None) -> tuple[Decimal, str, int]:
    """Montant, libellé et crédits d'un achat ; un pack doit être l'un de ceux du catalogue."""
    if cycle == "usage":
        if pack not in CREDIT_PACKS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Pack de crédits inconnu")
        return plan.credit * pack, f"{pack} crédits, formule {plan.id}", pack
    return plan.price(cycle), f"Formule {plan.id}, {'1 an' if cycle == 'annual' else '1 mois'}", 0


async def _ensure_members_fit(session: AsyncSession, org_id: UUID, plan: Plan) -> None:
    if plan.max_members is not None and await count_members(session, org_id) > plan.max_members:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cette formule est limitée à {plan.max_members} membre(s) : retirez d'abord des "
            "membres de l'espace.",
        )


def new_payment(
    org_id: UUID,
    *,
    plan_id: str,
    cycle: str,
    pack: int | None,
    method: str,
    user_id: UUID | None,
    amount: Decimal | None = None,
) -> Payment:
    """Paiement en attente pour la formule choisie, au prix du catalogue sauf montant donné."""
    plan = get_plan(plan_id)
    price, description, credits = _plan_and_amount(plan, cycle, pack)
    prefix = "SIM" if method == "online" else "WM"
    return Payment(
        organization_id=org_id,
        plan=plan.id,
        cycle=cycle,
        amount=(price if amount is None else amount).quantize(Decimal("0.01")),
        currency=CURRENCY,
        credits=credits,
        description=description,
        provider=PROVIDER if method == "online" else "manual",
        reference=f"{prefix}-{secrets.token_hex(4 if prefix == 'WM' else 6).upper()}",
        paid_by=user_id,
        status=PaymentStatus.PENDING,
        method=method,
        note="",
        created_at=datetime.now(UTC),
    )


async def mark_paid(
    session: AsyncSession, sub: Subscription, payment: Payment, *, recorded_by: UUID | None = None
) -> None:
    """Encaisse : numéro de reçu, puis la formule payée s'applique à l'espace."""
    if payment.status != PaymentStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ce paiement n'est plus en attente")
    await _ensure_members_fit(session, sub.organization_id, get_plan(payment.plan))
    now = datetime.now(UTC)
    number = await session.scalar(RECEIPT_SEQUENCE.next_value())
    payment.status = PaymentStatus.PAID
    payment.paid_at = now
    payment.receipt_number = f"WM-{now:%Y}-{number:06d}"
    if recorded_by is not None:
        payment.recorded_by = recorded_by
    _apply(sub, payment, now)
    await session.flush()


def _apply(sub: Subscription, payment: Payment, now: datetime) -> None:
    if payment.cycle == "usage":
        sub.credits += payment.credits
        sub.current_period_end = None
    else:
        # Un renouvellement de la même formule prolonge la période en cours.
        renewing = (
            sub.plan == payment.plan
            and sub.cycle == payment.cycle
            and sub.status == "active"
            and sub.current_period_end is not None
            and sub.current_period_end > now
        )
        start = sub.current_period_end if renewing and sub.current_period_end else now
        sub.current_period_end = start + period(payment.cycle)
    sub.plan, sub.cycle, sub.status = payment.plan, payment.cycle, "active"
    sub.trial_ends_at = None
    sub.cancel_at_period_end = False


async def checkout(
    session: AsyncSession,
    sub: Subscription,
    *,
    plan_id: str,
    cycle: str,
    pack: int | None,
    user_id: UUID,
    method: str = "online",
) -> Payment:
    """Paiement en ligne (prestataire simulé, encaissé tout de suite) ou annonce d'un virement
    ou d'un envoi mobile money, qui reste en attente jusqu'à sa confirmation."""
    plan = get_plan(plan_id)
    await _ensure_members_fit(session, sub.organization_id, plan)
    payment = new_payment(
        sub.organization_id, plan_id=plan.id, cycle=cycle, pack=pack, method=method, user_id=user_id
    )
    session.add(payment)
    await session.flush()
    if method == "online":
        await mark_paid(session, sub, payment)
    return payment


async def refund(
    session: AsyncSession, sub: Subscription, payment: Payment, *, recorded_by: UUID, note: str
) -> None:
    """Rembourse un paiement encaissé ; les crédits achetés non consommés sont retirés. La
    formule n'est pas retirée d'office : l'administration ajuste l'abonnement si besoin."""
    if payment.status != PaymentStatus.PAID:
        raise HTTPException(status.HTTP_409_CONFLICT, "Seul un paiement encaissé se rembourse")
    payment.status = PaymentStatus.REFUNDED
    payment.refunded_at = datetime.now(UTC)
    payment.recorded_by = recorded_by
    payment.note = note[:500]
    if payment.credits:
        sub.credits = max(0, sub.credits - payment.credits)
    await session.flush()
