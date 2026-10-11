"""SMS et WhatsApp de la redevabilité : configuration visible des membres, URL de réception."""

import hmac
import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.api.deps import AnyMember
from app.core.config import get_settings
from app.core.db import system_session
from app.schemas.accountability import ChannelConfig, SmsConfig
from app.services import sms

router = APIRouter(tags=["redevabilité"])

TWIML_EMPTY = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


@router.get("/orgs/{org_id}/sms/config", response_model=SmsConfig)
async def sms_config(org_id: UUID, _: AnyMember) -> SmsConfig:
    settings = get_settings()
    channels = []
    for channel in ("sms", "whatsapp"):
        configured = settings.sms_provider if channel == "sms" else settings.whatsapp_provider
        error = ""
        try:
            provider = sms.get_gateway(settings, channel).name
        except sms.SmsError as exc:
            provider, error = configured, str(exc)
        channels.append(
            ChannelConfig(
                channel=channel, provider=provider, simulated=provider == "simulated", error=error
            )
        )
    return SmsConfig(
        channels=channels,
        sender=settings.sms_sender,
        inbound_enabled=bool(settings.sms_webhook_token),
    )


def _check_token(token: str) -> None:
    expected = get_settings().sms_webhook_token
    if not expected or not hmac.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Introuvable")


def _gateway(channel: str) -> sms.SmsGateway:
    try:
        return sms.get_gateway(channel=channel)
    except sms.SmsError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


async def _payload(request: Request, raw: bytes) -> dict[str, Any]:
    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            payload = json.loads(raw or b"{}")
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "JSON invalide") from exc
        return payload if isinstance(payload, dict) else {}
    return {k: str(v) for k, v in (await request.form()).items()}


async def _receive(gateway: sms.SmsGateway, data: dict[str, Any]) -> Response:
    try:
        messages = gateway.parse_inbound(data)
    except sms.SmsError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    async with system_session() as session:
        for inbound in messages:
            await sms.route_inbound(session, inbound, gateway.name, gateway.channel)
        await session.commit()
    if gateway.name == "twilio":
        return Response(TWIML_EMPTY, media_type="application/xml")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sms/inbound/{token}", include_in_schema=False)
async def sms_inbound(token: str, request: Request) -> Response:
    """Appelée par le prestataire à chaque SMS reçu ; le secret de l'URL tient lieu d'accès."""
    _check_token(token)
    gateway = _gateway("sms")
    return await _receive(gateway, await _payload(request, await request.body()))


@router.get("/whatsapp/inbound/{token}", include_in_schema=False)
async def whatsapp_verify(token: str, request: Request) -> Response:
    """Vérification de l'URL par Meta : renvoyer `hub.challenge` si le jeton correspond."""
    _check_token(token)
    params = request.query_params
    verify = params.get("hub.verify_token", "")
    if params.get("hub.mode") != "subscribe" or not hmac.compare_digest(
        verify.encode(), token.encode()
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Jeton de vérification incorrect")
    return Response(params.get("hub.challenge", ""), media_type="text/plain")


@router.post("/whatsapp/inbound/{token}", include_in_schema=False)
async def whatsapp_inbound(token: str, request: Request) -> Response:
    """Appelée par le prestataire WhatsApp (Twilio ou Meta) à chaque message reçu."""
    _check_token(token)
    gateway = _gateway("whatsapp")
    raw = await request.body()
    if isinstance(gateway, sms.MetaWhatsAppGateway) and not gateway.verify_signature(
        raw, request.headers.get("x-hub-signature-256")
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Signature incorrecte")
    return await _receive(gateway, await _payload(request, raw))
