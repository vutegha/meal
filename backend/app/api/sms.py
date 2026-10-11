"""SMS de la redevabilité : configuration visible des membres, URL de réception du prestataire."""

import hmac
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.api.deps import AnyMember
from app.core.config import get_settings
from app.core.db import system_session
from app.schemas.accountability import SmsConfig
from app.services import sms

router = APIRouter(tags=["redevabilité"])

TWIML_EMPTY = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


@router.get("/orgs/{org_id}/sms/config", response_model=SmsConfig)
async def sms_config(org_id: UUID, _: AnyMember) -> SmsConfig:
    settings = get_settings()
    error = ""
    try:
        provider = sms.get_gateway(settings).name
    except sms.SmsError as exc:
        provider, error = settings.sms_provider, str(exc)
    return SmsConfig(
        provider=provider,
        simulated=provider == "simulated",
        sender=settings.sms_sender,
        inbound_enabled=bool(settings.sms_webhook_token),
        error=error,
    )


@router.post("/sms/inbound/{token}", include_in_schema=False)
async def sms_inbound(token: str, request: Request) -> Response:
    """Appelée par le prestataire à chaque SMS reçu ; le secret de l'URL tient lieu d'accès."""
    expected = get_settings().sms_webhook_token
    if not expected or not hmac.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Introuvable")
    try:
        gateway = sms.get_gateway()
    except sms.SmsError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    if request.headers.get("content-type", "").startswith("application/json"):
        payload = await request.json()
        data = {str(k): str(v) for k, v in payload.items()} if isinstance(payload, dict) else {}
    else:
        data = {k: str(v) for k, v in (await request.form()).items()}
    try:
        inbound = gateway.parse_inbound(data)
    except sms.SmsError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    async with system_session() as session:
        await sms.route_inbound(session, inbound, gateway.name)
        await session.commit()
    if gateway.name == "twilio":
        return Response(TWIML_EMPTY, media_type="application/xml")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
