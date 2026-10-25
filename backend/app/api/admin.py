"""Administration de la plateforme : abonnements de tous les espaces.

Réservé aux comptes `is_platform_admin` (accordé avec `python -m app.scripts.platform_admin`).
Les autres reçoivent 404, comme pour une route qui n'existe pas.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, SessionDep
from app.core.db import bind_system
from app.models import (
    AiCall,
    Membership,
    Organization,
    Payment,
    PaymentStatus,
    Project,
    Role,
    Subscription,
    User,
)
from app.schemas.admin import (
    AdminPaymentConfirm,
    AdminPaymentRecord,
    AdminPaymentRefund,
    AdminPaymentRow,
    AdminPayments,
    AdminPaymentsSummary,
    AdminSubscriptionRow,
    AdminSubscriptions,
    AdminSubscriptionUpdate,
    AdminSummary,
)
from app.schemas.billing import PaymentOut
from app.services import audit, receipts
from app.services import billing as svc

router = APIRouter(prefix="/admin", tags=["administration"])


async def require_platform_admin(user: CurrentUser, session: SessionDep) -> User:
    if not user.is_platform_admin:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")
    await bind_system(session)
    return user


PlatformAdmin = Annotated[User, Depends(require_platform_admin)]


async def _counts(session: AsyncSession, column: Any, where: Any = None) -> dict[UUID, int]:
    query = select(column, func.count()).group_by(column)
    if where is not None:
        query = query.where(where)
    return {org_id: count for org_id, count in (await session.execute(query)).all()}


async def _rows(
    session: AsyncSession, org_ids: list[UUID] | None = None
) -> list[AdminSubscriptionRow]:
    query = select(Organization).order_by(Organization.created_at.desc())
    if org_ids is not None:
        query = query.where(Organization.id.in_(org_ids))
    orgs = list(await session.scalars(query))
    members = await _counts(session, Membership.organization_id)
    projects = await _counts(session, Project.organization_id)
    credits_used = await _counts(
        session,
        AiCall.organization_id,
        (AiCall.status == "ok")
        & AiCall.purpose.in_(svc.CREDIT_PURPOSES)
        & (AiCall.created_at >= svc.month_start()),
    )
    payments = {
        org_id: (last, total)
        for org_id, last, total in (
            await session.execute(
                select(Payment.organization_id, func.max(Payment.paid_at), func.sum(Payment.amount))
                .where(Payment.status == PaymentStatus.PAID)
                .group_by(Payment.organization_id)
            )
        ).all()
    }
    contacts: dict[UUID, User] = {}
    for org_id, user in (
        await session.execute(
            select(Membership.organization_id, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.role == Role.ADMIN)
            .order_by(Membership.created_at)
        )
    ).all():
        contacts.setdefault(org_id, user)

    rows = []
    for org in orgs:
        sub = org.subscription or await svc.get_subscription(session, org.id)
        plan = svc.PLANS[sub.plan]
        contact = contacts.get(org.id)
        last, total = payments.get(org.id, (None, Decimal("0")))
        rows.append(
            AdminSubscriptionRow(
                organization_id=org.id,
                organization_name=org.name,
                organization_created_at=org.created_at,
                contact_email=contact.email if contact else None,
                contact_name=contact.full_name if contact else None,
                plan=sub.plan,
                account_type=plan.account_type,
                cycle=sub.cycle,
                status=svc.effective_status(sub),
                trial_ends_at=sub.trial_ends_at,
                current_period_end=sub.current_period_end,
                cancel_at_period_end=sub.cancel_at_period_end,
                credits=sub.credits,
                members=members.get(org.id, 0),
                projects=projects.get(org.id, 0),
                credits_used_this_month=credits_used.get(org.id, 0),
                last_payment_at=last,
                total_paid=(total or Decimal("0")).quantize(Decimal("0.01")),
            )
        )
    return rows


def _summary(rows: list[AdminSubscriptionRow], revenue: Decimal) -> AdminSummary:
    by_status = dict.fromkeys(("trialing", "active", "canceled", "expired"), 0)
    by_plan = dict.fromkeys(svc.PLANS, 0)
    recurring = Decimal("0")
    for row in rows:
        by_status[row.status] += 1
        by_plan[row.plan] = by_plan.get(row.plan, 0) + 1
        plan = svc.PLANS[row.plan]
        if row.status == "active" and row.cycle == "monthly":
            recurring += plan.monthly
        elif row.status == "active" and row.cycle == "annual":
            recurring += plan.annual / 12
    return AdminSummary(
        organizations=len(rows),
        by_status=by_status,
        by_plan=by_plan,
        monthly_recurring=recurring.quantize(Decimal("0.01")),
        revenue_last_30_days=revenue.quantize(Decimal("0.01")),
        currency=svc.CURRENCY,
    )


@router.get("/subscriptions", response_model=AdminSubscriptions)
async def list_subscriptions(
    _: PlatformAdmin,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    status_: Annotated[str | None, Query(alias="status")] = None,
    plan: str | None = None,
) -> AdminSubscriptions:
    """Tous les espaces, leur formule et leur usage. Les filtres ne changent pas le résumé."""
    rows = await _rows(session)
    revenue = await session.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.status == PaymentStatus.PAID,
            Payment.paid_at >= datetime.now(UTC) - timedelta(days=30),
        )
    )
    summary = _summary(rows, Decimal(revenue or 0))
    if q:
        needle = q.strip().lower()
        rows = [
            r
            for r in rows
            if needle in r.organization_name.lower()
            or needle in (r.contact_email or "").lower()
            or needle in (r.contact_name or "").lower()
        ]
    if status_:
        rows = [r for r in rows if r.status == status_]
    if plan:
        rows = [r for r in rows if r.plan == plan]
    await session.commit()
    return AdminSubscriptions(summary=summary, items=rows)


@router.patch("/subscriptions/{org_id}", response_model=AdminSubscriptionRow)
async def update_subscription(
    org_id: UUID, body: AdminSubscriptionUpdate, admin: PlatformAdmin, session: SessionDep
) -> AdminSubscriptionRow:
    """Change la formule, les dates ou les crédits d'un espace, sans paiement (geste commercial,
    paiement reçu hors ligne, correction). Chaque changement est inscrit au journal de l'espace."""
    if await session.get(Organization, org_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Espace introuvable")
    sub = await svc.get_subscription(session, org_id)
    before = _snapshot(sub)
    now = datetime.now(UTC)

    if body.plan is not None and body.plan != sub.plan:
        plan = svc.get_plan(body.plan)
        members = await svc.count_members(session, org_id)
        if plan.max_members is not None and members > plan.max_members:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Cette formule est limitée à {plan.max_members} membre(s) et l'espace en "
                f"compte {members}.",
            )
        sub.plan = plan.id
    if body.cycle is not None:
        sub.cycle = body.cycle
    if body.status is not None:
        sub.status = body.status
    if "trial_ends_at" in body.model_fields_set:
        sub.trial_ends_at = body.trial_ends_at
    if "current_period_end" in body.model_fields_set:
        sub.current_period_end = body.current_period_end
    if sub.status == "trialing" and sub.trial_ends_at is None:
        sub.trial_ends_at = now + timedelta(days=svc.TRIAL_DAYS)
    if sub.status == "active" and sub.cycle != "usage" and sub.current_period_end is None:
        sub.current_period_end = now + svc.period(sub.cycle)
    if body.extend_days:
        field = "trial_ends_at" if sub.status == "trialing" else "current_period_end"
        end = getattr(sub, field)
        setattr(sub, field, max(end or now, now) + timedelta(days=body.extend_days))
    if body.add_credits:
        sub.credits = max(0, sub.credits + body.add_credits)
    if body.cancel_at_period_end is not None:
        sub.cancel_at_period_end = body.cancel_at_period_end

    after = _snapshot(sub)
    audit.record(
        session,
        organization_id=org_id,
        actor_id=admin.id,
        action="subscription.admin_updated",
        entity_type="subscription",
        entity_id=sub.id,
        data={
            "before": before,
            "after": after,
            **({"note": body.note} if body.note else {}),
        },
    )
    await session.flush()
    [row] = await _rows(session, [org_id])
    await session.commit()
    return row


def _snapshot(sub: Subscription) -> dict[str, object]:
    return {
        "plan": sub.plan,
        "cycle": sub.cycle,
        "status": sub.status,
        "trial_ends_at": sub.trial_ends_at.isoformat() if sub.trial_ends_at else None,
        "current_period_end": (
            sub.current_period_end.isoformat() if sub.current_period_end else None
        ),
        "credits": sub.credits,
        "cancel_at_period_end": sub.cancel_at_period_end,
    }


# --- Paiements -----------------------------------------------------------------------------


async def _payment_rows(session: AsyncSession, query: Any) -> list[AdminPaymentRow]:
    rows = await session.execute(
        query.add_columns(Organization.name, User.email)
        .join(Organization, Organization.id == Payment.organization_id)
        .outerjoin(User, User.id == Payment.paid_by)
    )
    return [
        AdminPaymentRow(
            **PaymentOut.model_validate(payment).model_dump(),
            organization_id=payment.organization_id,
            organization_name=name,
            paid_by_email=email,
        )
        for payment, name, email in rows.all()
    ]


async def _sum(session: AsyncSession, *where: Any) -> Decimal:
    total = await session.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(*where))
    return Decimal(total or 0).quantize(Decimal("0.01"))


@router.get("/payments", response_model=AdminPayments)
async def list_payments(
    _: PlatformAdmin,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    status_: Annotated[str | None, Query(alias="status")] = None,
) -> AdminPayments:
    """Tous les paiements, les plus récents d'abord ; ceux en attente sont à confirmer."""
    query = select(Payment).order_by(Payment.created_at.desc(), Payment.id).limit(500)
    if status_:
        query = query.where(Payment.status == status_)
    if q:
        needle = f"%{q.strip()}%"
        query = query.where(
            Organization.name.ilike(needle)
            | Payment.reference.ilike(needle)
            | Payment.receipt_number.ilike(needle)
            | User.email.ilike(needle)
        )
    items = await _payment_rows(session, query)
    since = datetime.now(UTC) - timedelta(days=30)
    pending = await session.scalar(
        select(func.count()).select_from(Payment).where(Payment.status == PaymentStatus.PENDING)
    )
    summary = AdminPaymentsSummary(
        pending=pending or 0,
        pending_amount=await _sum(session, Payment.status == PaymentStatus.PENDING),
        paid_last_30_days=await _sum(
            session, Payment.status == PaymentStatus.PAID, Payment.paid_at >= since
        ),
        refunded_last_30_days=await _sum(
            session, Payment.status == PaymentStatus.REFUNDED, Payment.refunded_at >= since
        ),
        currency=svc.CURRENCY,
    )
    await session.commit()
    return AdminPayments(summary=summary, items=items)


async def _get_payment(session: AsyncSession, payment_id: UUID) -> Payment:
    payment = await session.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paiement introuvable")
    return payment


async def _row(session: AsyncSession, payment: Payment) -> AdminPaymentRow:
    [row] = await _payment_rows(session, select(Payment).where(Payment.id == payment.id))
    return row


def _log(session: AsyncSession, admin: User, payment: Payment, action: str, **data: object) -> None:
    audit.record(
        session,
        organization_id=payment.organization_id,
        actor_id=admin.id,
        action=action,
        entity_type="payment",
        entity_id=payment.id,
        data={
            "amount": str(payment.amount),
            "reference": payment.reference,
            "receipt_number": payment.receipt_number,
            **data,
        },
    )


@router.post("/payments/{payment_id}/confirm", response_model=AdminPaymentRow)
async def confirm_payment(
    payment_id: UUID, body: AdminPaymentConfirm, admin: PlatformAdmin, session: SessionDep
) -> AdminPaymentRow:
    """Le virement ou l'envoi mobile money annoncé est arrivé : la formule s'applique."""
    payment = await _get_payment(session, payment_id)
    sub = await svc.get_subscription(session, payment.organization_id)
    if body.method:
        payment.method = body.method
    if body.note:
        payment.note = body.note
    await svc.mark_paid(session, sub, payment, recorded_by=admin.id)
    _log(session, admin, payment, "payment.confirmed", method=payment.method, note=body.note)
    row = await _row(session, payment)
    await session.commit()
    return row


@router.post("/payments/{payment_id}/refund", response_model=AdminPaymentRow)
async def refund_payment(
    payment_id: UUID, body: AdminPaymentRefund, admin: PlatformAdmin, session: SessionDep
) -> AdminPaymentRow:
    payment = await _get_payment(session, payment_id)
    sub = await svc.get_subscription(session, payment.organization_id)
    await svc.refund(session, sub, payment, recorded_by=admin.id, note=body.note)
    _log(session, admin, payment, "payment.refunded", note=body.note)
    row = await _row(session, payment)
    await session.commit()
    return row


@router.post(
    "/subscriptions/{org_id}/payments",
    response_model=AdminPaymentRow,
    status_code=status.HTTP_201_CREATED,
)
async def record_payment(
    org_id: UUID, body: AdminPaymentRecord, admin: PlatformAdmin, session: SessionDep
) -> AdminPaymentRow:
    """Enregistre un paiement reçu hors de l'application ; la formule payée s'applique."""
    if await session.get(Organization, org_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Espace introuvable")
    sub = await svc.get_subscription(session, org_id)
    payment = svc.new_payment(
        org_id,
        plan_id=body.plan,
        cycle=body.cycle,
        pack=body.pack,
        method=body.method,
        user_id=None,
        amount=body.amount,
    )
    if body.reference.strip():
        payment.reference = body.reference.strip()
    payment.note = body.note
    session.add(payment)
    await session.flush()
    await svc.mark_paid(session, sub, payment, recorded_by=admin.id)
    _log(session, admin, payment, "payment.recorded", method=payment.method, note=body.note)
    row = await _row(session, payment)
    await session.commit()
    return row


@router.get("/payments/{payment_id}/receipt.pdf")
async def admin_receipt(payment_id: UUID, _: PlatformAdmin, session: SessionDep) -> Response:
    payment = await _get_payment(session, payment_id)
    organization = await session.get(Organization, payment.organization_id)
    assert organization is not None
    content = await receipts.pdf(payment, organization)
    return Response(content, media_type="application/pdf", headers=receipts.headers(payment))
