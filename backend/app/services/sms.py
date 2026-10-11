"""Passerelle SMS de la redevabilité : envoi aux personnes qui ont fait un retour, réception.

Le prestataire se choisit par `SMS_PROVIDER` : "simulated" (par défaut, aucun SMS ne part,
utile en développement et en démonstration), "twilio" ou "africastalking". Chaque adaptateur
sait envoyer un SMS et lire la requête que le prestataire adresse à l'URL de réception.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Protocol
from uuid import UUID, uuid4

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.models import (
    FeedbackCategory,
    FeedbackChannel,
    FeedbackEntry,
    Project,
    SmsDirection,
    SmsMessage,
)
from app.services import audit

# Quatre segments au plus : au-delà, le coût et le risque de coupure augmentent.
MAX_BODY_CHARS = 640
TIMEOUT = httpx.Timeout(15.0)


class SmsError(Exception):
    """Envoi refusé ou prestataire injoignable ; le message est lisible par l'utilisateur."""


@dataclass
class SendResult:
    provider_message_id: str
    status: str = "sent"


@dataclass
class InboundSms:
    phone: str
    body: str
    provider_message_id: str = ""


class SmsGateway(Protocol):
    name: str

    async def send(self, to: str, body: str) -> SendResult: ...

    def parse_inbound(self, data: Mapping[str, str]) -> InboundSms: ...


def normalize_phone(value: str) -> str | None:
    """« +243 99 000-0000 » → « +243990000000 » ; None si ce n'est pas un numéro."""
    phone = re.sub(r"[\s().\-/]", "", value or "")
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    return phone if re.fullmatch(r"\+?\d{8,15}", phone) else None


def _required(data: Mapping[str, str], *keys: str) -> str:
    for key in keys:
        if data.get(key):
            return str(data[key])
    raise SmsError(f"Champ « {keys[0]} » absent de la requête du prestataire")


class SimulatedGateway:
    """Aucun envoi réel : le SMS est enregistré comme envoyé."""

    name = "simulated"

    async def send(self, to: str, body: str) -> SendResult:
        return SendResult(provider_message_id=f"sim-{uuid4().hex[:12]}")

    def parse_inbound(self, data: Mapping[str, str]) -> InboundSms:
        return InboundSms(
            phone=_required(data, "from", "phone"),
            body=_required(data, "text", "body"),
            provider_message_id=str(data.get("id", "")),
        )


class TwilioGateway:
    name = "twilio"

    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        sender: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.sender = sender
        self.transport = transport

    async def send(self, to: str, body: str) -> SendResult:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=TIMEOUT) as client:
                r = await client.post(
                    url,
                    auth=(self.account_sid, self.auth_token),
                    data={"To": to, "From": self.sender, "Body": body},
                )
        except httpx.HTTPError as exc:
            raise SmsError("Twilio est injoignable, réessayez plus tard") from exc
        data = r.json() if r.content else {}
        if r.status_code >= 400:
            raise SmsError(f"Twilio a refusé l'envoi : {data.get('message', r.status_code)}")
        return SendResult(provider_message_id=str(data.get("sid", "")))

    def parse_inbound(self, data: Mapping[str, str]) -> InboundSms:
        return InboundSms(
            phone=_required(data, "From"),
            body=str(data.get("Body", "")),
            provider_message_id=str(data.get("MessageSid", "")),
        )


class AfricasTalkingGateway:
    name = "africastalking"

    def __init__(
        self,
        username: str,
        api_key: str,
        sender: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.username = username
        self.api_key = api_key
        self.sender = sender
        self.transport = transport

    async def send(self, to: str, body: str) -> SendResult:
        host = (
            "api.sandbox.africastalking.com"
            if self.username == "sandbox"
            else "api.africastalking.com"
        )
        form = {"username": self.username, "to": to, "message": body}
        if self.sender:
            form["from"] = self.sender
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=TIMEOUT) as client:
                r = await client.post(
                    f"https://{host}/version1/messaging",
                    headers={"apiKey": self.api_key, "Accept": "application/json"},
                    data=form,
                )
        except httpx.HTTPError as exc:
            raise SmsError("Africa's Talking est injoignable, réessayez plus tard") from exc
        if r.status_code >= 400:
            raise SmsError(f"Africa's Talking a refusé l'envoi : {r.text[:200]}")
        recipients = r.json().get("SMSMessageData", {}).get("Recipients", [])
        # 100 : traité, 101 : envoyé, 102 : en file d'attente.
        if not recipients or recipients[0].get("statusCode") not in (100, 101, 102):
            status = recipients[0].get("status") if recipients else "aucun destinataire"
            raise SmsError(f"Africa's Talking a refusé l'envoi : {status}")
        return SendResult(provider_message_id=str(recipients[0].get("messageId", "")))

    def parse_inbound(self, data: Mapping[str, str]) -> InboundSms:
        return InboundSms(
            phone=_required(data, "from"),
            body=str(data.get("text", "")),
            provider_message_id=str(data.get("id", "")),
        )


def get_gateway(settings: Settings | None = None) -> SmsGateway:
    settings = settings or get_settings()
    provider = settings.sms_provider.strip().lower()
    if provider == "twilio":
        if not (settings.twilio_account_sid and settings.twilio_auth_token and settings.sms_sender):
            raise SmsError(
                "Twilio n'est pas configuré : TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN et SMS_SENDER"
            )
        return TwilioGateway(
            settings.twilio_account_sid, settings.twilio_auth_token, settings.sms_sender
        )
    if provider == "africastalking":
        if not (settings.africastalking_username and settings.africastalking_api_key):
            raise SmsError(
                "Africa's Talking n'est pas configuré : "
                "AFRICASTALKING_USERNAME et AFRICASTALKING_API_KEY"
            )
        return AfricasTalkingGateway(
            settings.africastalking_username, settings.africastalking_api_key, settings.sms_sender
        )
    if provider == "simulated":
        return SimulatedGateway()
    raise SmsError(f"Prestataire SMS inconnu : {settings.sms_provider}")


# --- Réception ---------------------------------------------------------------------------


async def next_reference(session: AsyncSession, project_id: UUID) -> str:
    count = await session.scalar(select(func.count()).where(FeedbackEntry.project_id == project_id))
    return f"RET-{(count or 0) + 1:04d}"


async def route_inbound(session: AsyncSession, inbound: InboundSms, provider: str) -> SmsMessage:
    """Range un SMS reçu (session système : on ne sait pas encore de quelle organisation il vient).

    1. Le numéro a déjà reçu un SMS au sujet d'un retour : la réponse rejoint cet échange.
    2. Sinon, un SMS qui commence par le code d'un projet crée un nouveau retour dans ce projet.
    3. Sinon il est conservé sans organisation, invisible des utilisateurs.
    """
    if inbound.provider_message_id:
        duplicate = await session.scalar(
            select(SmsMessage).where(
                SmsMessage.provider == provider,
                SmsMessage.provider_message_id == inbound.provider_message_id,
                SmsMessage.direction == SmsDirection.INBOUND,
            )
        )
        if duplicate is not None:  # le prestataire renvoie une notification déjà reçue
            return duplicate

    phone = normalize_phone(inbound.phone) or inbound.phone.strip()[:32]
    text = inbound.body.strip()
    message = SmsMessage(
        direction=SmsDirection.INBOUND,
        phone=phone,
        body=text,
        status="received",
        provider=provider,
        provider_message_id=inbound.provider_message_id[:100],
    )
    last = await session.scalar(
        select(SmsMessage)
        .where(
            SmsMessage.phone == phone,
            SmsMessage.direction == SmsDirection.OUTBOUND,
            SmsMessage.feedback_id.is_not(None),
        )
        .order_by(SmsMessage.created_at.desc())
        .limit(1)
    )
    if last is not None:
        message.organization_id = last.organization_id
        message.project_id = last.project_id
        message.feedback_id = last.feedback_id
    else:
        code, _, rest = text.partition(" ")
        projects = (
            list(
                await session.scalars(
                    select(Project).where(func.upper(Project.code) == code.upper())
                )
            )
            if code
            else []
        )
        # Un code porté par plusieurs organisations ne permet pas de choisir : on s'abstient.
        if len(projects) == 1:
            project = projects[0]
            entry = FeedbackEntry(
                organization_id=project.organization_id,
                project_id=project.id,
                reference=await next_reference(session, project.id),
                received_on=date.today(),
                channel=FeedbackChannel.SMS,
                # À qualifier par l'équipe, comme tout retour reçu sans saisie.
                category=FeedbackCategory.OTHER,
                sensitive=False,
                description=rest.strip() or text,
                contact=phone,
            )
            session.add(entry)
            await session.flush()
            audit.record(
                session,
                organization_id=project.organization_id,
                actor_id=None,
                action="feedback.recorded",
                entity_type="feedback",
                entity_id=entry.id,
                data={"reference": entry.reference, "channel": "sms"},
            )
            message.organization_id = project.organization_id
            message.project_id = project.id
            message.feedback_id = entry.id
    session.add(message)
    await session.flush()
    return message


async def summaries(session: AsyncSession, project_id: UUID) -> dict[UUID, tuple[int, bool]]:
    """Par retour : nombre de SMS, et si le dernier vient de la personne (réponse attendue)."""
    rows = await session.execute(
        select(SmsMessage.feedback_id, SmsMessage.direction)
        .where(SmsMessage.project_id == project_id, SmsMessage.feedback_id.is_not(None))
        .order_by(SmsMessage.created_at)
    )
    result: dict[UUID, tuple[int, bool]] = {}
    for feedback_id, direction in rows:
        if feedback_id is None:
            continue
        count, _ = result.get(feedback_id, (0, False))
        result[feedback_id] = (count + 1, direction == SmsDirection.INBOUND)
    return result
