from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import AnyMember, OrgAdmin, SessionDep
from app.models import Payment, Subscription
from app.schemas.billing import (
    BillingUsage,
    Catalog,
    CheckoutIn,
    CheckoutOut,
    PaymentOut,
    PlanLimits,
    PlanOut,
    PlanPrices,
    SubscriptionOut,
)
from app.services import audit
from app.services import billing as svc
from app.services.ai import month_cost

router = APIRouter(tags=["abonnements"])


def _limits(plan: svc.Plan) -> PlanLimits:
    return PlanLimits(
        projects=plan.max_projects,
        members=plan.max_members,
        ai_monthly_budget_usd=plan.ai_monthly_budget_usd,
    )


@router.get("/billing/plans", response_model=Catalog)
async def catalog() -> Catalog:
    """Formules et tarifs, publics : la page Tarifs du site les affiche sans connexion."""
    return Catalog(
        currency=svc.CURRENCY,
        trial_days=svc.TRIAL_DAYS,
        welcome_credits=svc.WELCOME_CREDITS,
        credit_packs=list(svc.CREDIT_PACKS),
        plans=[
            PlanOut(
                id=plan.id,
                account_type=plan.account_type,
                prices=PlanPrices(monthly=plan.monthly, annual=plan.annual, credit=plan.credit),
                limits=_limits(plan),
                features=list(plan.features),
            )
            for plan in svc.PLANS.values()
        ],
    )


async def _out(session: SessionDep, sub: Subscription) -> SubscriptionOut:
    plan = svc.PLANS[sub.plan]
    org_id = sub.organization_id
    return SubscriptionOut(
        plan=sub.plan,
        account_type=plan.account_type,
        cycle=sub.cycle,
        status=svc.effective_status(sub),
        trial_ends_at=sub.trial_ends_at,
        current_period_end=sub.current_period_end,
        credits=sub.credits,
        cancel_at_period_end=sub.cancel_at_period_end,
        limits=_limits(plan),
        features=list(plan.features),
        usage=BillingUsage(
            projects=await svc.count_projects(session, org_id),
            members=await svc.count_members(session, org_id),
            ai_month_cost_usd=await month_cost(session, org_id),
        ),
    )


@router.get("/orgs/{org_id}/billing", response_model=SubscriptionOut)
async def get_billing(org_id: UUID, _: AnyMember, session: SessionDep) -> SubscriptionOut:
    sub = await svc.get_subscription(session, org_id)
    out = await _out(session, sub)
    await session.commit()
    return out


@router.post("/orgs/{org_id}/billing/checkout", response_model=CheckoutOut)
async def checkout(
    org_id: UUID, body: CheckoutIn, admin: OrgAdmin, session: SessionDep
) -> CheckoutOut:
    sub = await svc.get_subscription(session, org_id)
    payment = await svc.checkout(
        session, sub, plan_id=body.plan, cycle=body.cycle, pack=body.pack, user_id=admin.user_id
    )
    audit.record(
        session,
        organization_id=org_id,
        actor_id=admin.user_id,
        action="subscription.paid",
        entity_type="payment",
        entity_id=payment.id,
        data={
            "plan": payment.plan,
            "cycle": payment.cycle,
            "amount": str(payment.amount),
            "reference": payment.reference,
        },
    )
    out = CheckoutOut(
        payment=PaymentOut.model_validate(payment), subscription=await _out(session, sub)
    )
    await session.commit()
    return out


@router.post("/orgs/{org_id}/billing/cancel", response_model=SubscriptionOut)
async def cancel(org_id: UUID, admin: OrgAdmin, session: SessionDep) -> SubscriptionOut:
    """Arrête le renouvellement : l'espace garde sa formule jusqu'à la fin de la période."""
    sub = await svc.get_subscription(session, org_id)
    if sub.cycle == "usage" or svc.effective_status(sub) == "expired":
        raise HTTPException(status.HTTP_409_CONFLICT, "Aucun abonnement en cours à résilier")
    sub.cancel_at_period_end = True
    audit.record(
        session,
        organization_id=org_id,
        actor_id=admin.user_id,
        action="subscription.canceled",
        entity_type="subscription",
        entity_id=sub.id,
        data={"plan": sub.plan, "cycle": sub.cycle},
    )
    out = await _out(session, sub)
    await session.commit()
    return out


@router.get("/orgs/{org_id}/billing/payments", response_model=list[PaymentOut])
async def list_payments(org_id: UUID, _: OrgAdmin, session: SessionDep) -> list[Payment]:
    rows = await session.scalars(
        select(Payment)
        .where(Payment.organization_id == org_id)
        .order_by(Payment.created_at.desc(), Payment.id)
    )
    return list(rows)
