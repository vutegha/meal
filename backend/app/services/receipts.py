"""Reçu PDF d'un paiement encaissé ou remboursé, pour l'espace et l'administration."""

import asyncio
from decimal import Decimal

from fastapi import HTTPException, status

from app.documents.render import Layout, RenderedDocument, Section, to_pdf
from app.models import Organization, Payment, PaymentStatus

PLAN_NAMES = {"solo": "Solo", "team": "Équipe", "institution": "Institution"}
CYCLE_NAMES = {"monthly": "mensuelle", "annual": "annuelle", "usage": "à l'usage"}
METHOD_NAMES = {
    "online": "Paiement en ligne",
    "mobile_money": "Mobile money",
    "bank_transfer": "Virement bancaire",
    "cash": "Espèces",
    "other": "Autre",
}


def _money(amount: Decimal, currency: str) -> str:
    whole, _, cents = f"{amount:,.2f}".partition(".")
    return f"{whole.replace(',', ' ')},{cents} {currency}"


def document(payment: Payment, organization: Organization) -> RenderedDocument:
    paid_at = payment.paid_at or payment.created_at
    item = f"Formule {PLAN_NAMES.get(payment.plan, payment.plan)}, facturation " + CYCLE_NAMES.get(
        payment.cycle, payment.cycle
    )
    if payment.credits:
        item += f" : {payment.credits} crédits IA"
    content = (
        "| Désignation | Montant |\n|---|---|\n"
        f"| {item} | {_money(payment.amount, payment.currency)} |\n"
        f"| **Total payé** | **{_money(payment.amount, payment.currency)}** |"
    )
    sections = [Section("Détail", content)]
    if payment.status == PaymentStatus.REFUNDED and payment.refunded_at:
        sections.append(
            Section(
                "Remboursement",
                f"Ce paiement a été remboursé le {payment.refunded_at:%d/%m/%Y}."
                + (f" Motif : {payment.note}" if payment.note else ""),
            )
        )
    return RenderedDocument(
        title=f"Reçu {payment.receipt_number}",
        subtitle="We MEAL, abonnement à la plateforme",
        meta=[
            ("Espace", organization.name),
            ("Date de paiement", f"{paid_at:%d/%m/%Y}"),
            ("Moyen de paiement", METHOD_NAMES.get(payment.method, payment.method)),
            ("Référence", payment.reference),
        ],
        sections=sections,
        layout=Layout(footer=f"We MEAL · reçu {payment.receipt_number}"),
    )


async def pdf(payment: Payment, organization: Organization) -> bytes:
    if payment.receipt_number is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aucun reçu : paiement non encaissé")
    return await asyncio.to_thread(to_pdf, document(payment, organization))


def headers(payment: Payment) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="recu-{payment.receipt_number}.pdf"'}
