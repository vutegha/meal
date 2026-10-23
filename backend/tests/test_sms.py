import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import update

from app.core.config import Settings, get_settings
from app.models import SmsMessage
from app.services import sms
from tests.conftest import owner_engine, register
from tests.test_organizations import add_member, login
from tests.test_projects import create_project


async def setup(client: AsyncClient) -> tuple[dict[str, Any], str, dict[str, Any]]:
    ctx = await register(client, "pm@example.org")
    base = f"/api/v1/orgs/{ctx['org_id']}/projects/{await create_project(client, ctx, 'KIW')}"
    r = await client.post(
        f"{base}/feedback",
        headers=ctx["headers"],
        json={
            "channel": "hotline",
            "category": "complaint",
            "description": "Les kits sont arrivés incomplets.",
            "contact": "+243 99 000-0001",
        },
    )
    assert r.status_code == 201, r.text
    return ctx, base, r.json()


@pytest.fixture
def webhook(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(get_settings(), "sms_webhook_token", "secret-de-test")
    return "/api/v1/sms/inbound/secret-de-test"


def test_normalize_phone() -> None:
    assert sms.normalize_phone("+243 99 000-0001") == "+243990000001"
    assert sms.normalize_phone("00243 (99) 000.0001") == "+243990000001"
    assert sms.normalize_phone("appeler le chef") is None
    assert sms.normalize_phone("123") is None


async def test_send_and_receive_sms_on_feedback(client: AsyncClient, webhook: str) -> None:
    ctx, base, entry = await setup(client)
    h = ctx["headers"]
    config = (await client.get(f"/api/v1/orgs/{ctx['org_id']}/sms/config", headers=h)).json()
    assert [(c["channel"], c["simulated"]) for c in config["channels"]] == [
        ("sms", True),
        ("whatsapp", True),
    ]
    assert config["inbound_enabled"] is True

    url = f"{base}/feedback/{entry['id']}/sms"
    r = await client.post(url, headers=h, json={"body": "Bonjour, pouvez-vous préciser ?"})
    assert r.status_code == 201, r.text
    sent = r.json()
    assert sent["direction"] == "outbound" and sent["status"] == "sent"
    assert sent["phone"] == "+243990000001" and sent["provider"] == "simulated"

    # La réponse de la personne rejoint l'échange en cours.
    r = await client.post(webhook, data={"from": "+243990000001", "text": "Il manquait 3 bâches"})
    assert r.status_code == 204
    thread = (await client.get(url, headers=h)).json()
    assert [m["direction"] for m in thread] == ["outbound", "inbound"]
    assert thread[1]["body"] == "Il manquait 3 bâches"

    listed = (await client.get(f"{base}/feedback", headers=h)).json()[0]
    assert listed["sms_count"] == 2 and listed["sms_awaiting_reply"] is True
    assert listed["status"] == "in_progress"  # écrire à la personne lance le traitement


async def test_inbound_sms_with_project_code_creates_feedback(
    client: AsyncClient, webhook: str
) -> None:
    ctx, base, _ = await setup(client)
    body = {"from": "0024381000000", "text": "kiw Personne n'est venu au point d'eau", "id": "m1"}
    assert (await client.post(webhook, json=body)).status_code == 204
    # Notification renvoyée par le prestataire : pas de doublon.
    assert (await client.post(webhook, json=body)).status_code == 204
    # Ni conversation en cours ni code de projet : conservé, mais visible de personne.
    assert (
        await client.post(webhook, data={"from": "+243810000009", "text": "bonjour"})
    ).status_code == 204

    entries = (await client.get(f"{base}/feedback", headers=ctx["headers"])).json()
    assert len(entries) == 2
    created = next(e for e in entries if e["channel"] == "sms")
    assert created["reference"] == "RET-0002" and created["category"] == "other"
    assert created["description"] == "Personne n'est venu au point d'eau"
    # Message reçu, puis accusé de réception avec la notice d'information.
    assert created["contact"] == "+24381000000" and created["sms_count"] == 2
    thread = (
        await client.get(f"{base}/feedback/{created['id']}/sms", headers=ctx["headers"])
    ).json()
    assert [m["direction"] for m in thread] == ["inbound", "outbound"]
    assert "RET-0002" in thread[1]["body"] and "confidentielle" in thread[1]["body"]
    assert created["sms_awaiting_reply"] is True  # l'accusé automatique ne compte pas
    # Confidentiel jusqu'à sa qualification : il peut signaler un abus.
    assert created["sensitive"] is True
    await add_member(client, ctx, "suivi@example.org", "meal_officer")
    officer = await login(client, "suivi@example.org")
    seen = (await client.get(f"{base}/feedback", headers=officer)).json()
    assert [e["channel"] for e in seen] == ["hotline"]


async def test_reply_joins_only_recent_open_thread(client: AsyncClient, webhook: str) -> None:
    ctx, base, entry = await setup(client)
    h = ctx["headers"]
    url = f"{base}/feedback/{entry['id']}/sms"
    assert (await client.post(url, headers=h, json={"body": "Merci"})).status_code == 201

    # Retour clôturé : la réponse ne rejoint plus l'ancien dossier.
    r = await client.patch(
        f"{base}/feedback/{entry['id']}",
        headers=h,
        json={"status": "closed", "response": "Kits complétés"},
    )
    assert r.status_code == 200, r.text
    await client.post(webhook, data={"from": "+243990000001", "text": "Autre sujet"})
    assert len((await client.get(url, headers=h)).json()) == 1

    # Rouvert, mais le dernier envoi date de plus de 30 jours : même chose.
    await client.patch(f"{base}/feedback/{entry['id']}", headers=h, json={"status": "in_progress"})
    async with owner_engine.begin() as conn:
        await conn.execute(
            update(SmsMessage).values(created_at=datetime.now(UTC) - timedelta(days=31))
        )
    await client.post(webhook, data={"from": "+243990000001", "text": "Encore"})
    assert len((await client.get(url, headers=h)).json()) == 1


async def test_sms_permissions_and_errors(
    client: AsyncClient, webhook: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx, base, entry = await setup(client)
    h = ctx["headers"]
    url = f"{base}/feedback/{entry['id']}/sms"
    await add_member(client, ctx, "terrain@example.org", "field_agent")
    field = await login(client, "terrain@example.org")
    assert (await client.post(url, headers=field, json={"body": "x"})).status_code == 403
    assert (await client.get(url, headers=field)).status_code == 403

    assert (await client.post("/api/v1/sms/inbound/mauvais", data={})).status_code == 404

    r = await client.post(
        f"{base}/feedback",
        headers=h,
        json={"channel": "hotline", "category": "information", "description": "Anonyme"},
    )
    anonymous = f"{base}/feedback/{r.json()['id']}/sms"
    assert (await client.post(anonymous, headers=h, json={"body": "x"})).status_code == 422

    # Prestataire réel sans identifiants : l'échec est enregistré et lisible.
    monkeypatch.setattr(get_settings(), "sms_provider", "twilio")
    r = await client.post(url, headers=h, json={"body": "Bonjour"})
    assert r.status_code == 201 and r.json()["status"] == "failed"
    assert "TWILIO_ACCOUNT_SID" in r.json()["error"]
    simulate = await client.post(f"{url}/simulate", headers=h, json={"body": "ok"})
    assert simulate.status_code == 404


async def test_simulated_reply(client: AsyncClient) -> None:
    ctx, base, entry = await setup(client)
    url = f"{base}/feedback/{entry['id']}/sms"
    r = await client.post(f"{url}/simulate", headers=ctx["headers"], json={"body": "Merci"})
    assert r.status_code == 201 and r.json()["direction"] == "inbound"


async def test_twilio_adapter() -> None:
    sent: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent["url"] = str(request.url)
        sent["form"] = dict(httpx.QueryParams(request.content.decode()))
        return httpx.Response(201, json={"sid": "SM123", "status": "queued"})

    gateway = sms.TwilioGateway("AC1", "tok", "+15550000000", httpx.MockTransport(handler))
    result = await gateway.send("+243990000001", "Bonjour")
    assert result.provider_message_id == "SM123"
    assert sent["url"].endswith("/Accounts/AC1/Messages.json")
    assert sent["form"] == {"To": "+243990000001", "From": "+15550000000", "Body": "Bonjour"}
    [inbound] = gateway.parse_inbound({"From": "+243990000001", "Body": "Oui", "MessageSid": "SM9"})
    assert (inbound.phone, inbound.body, inbound.provider_message_id) == (
        "+243990000001",
        "Oui",
        "SM9",
    )

    refused = sms.TwilioGateway(
        "AC1",
        "tok",
        "+1555",
        httpx.MockTransport(lambda _: httpx.Response(400, json={"message": "Invalid To"})),
    )
    with pytest.raises(sms.SmsError, match="Invalid To"):
        await refused.send("+243990000001", "Bonjour")


async def test_africastalking_adapter() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.sandbox.africastalking.com"
        assert request.headers["apiKey"] == "key"
        recipients = [{"statusCode": 101, "status": "Success", "messageId": "ATXid_1"}]
        return httpx.Response(
            201, content=json.dumps({"SMSMessageData": {"Recipients": recipients}})
        )

    gateway = sms.AfricasTalkingGateway("sandbox", "key", "", httpx.MockTransport(handler))
    assert (await gateway.send("+243990000001", "Bonjour")).provider_message_id == "ATXid_1"
    [inbound] = gateway.parse_inbound({"from": "+243990000001", "text": "Oui", "id": "a"})
    assert inbound.body == "Oui"

    settings = Settings(sms_provider="africastalking")
    with pytest.raises(sms.SmsError, match="AFRICASTALKING_API_KEY"):
        sms.get_gateway(settings)


async def test_whatsapp_conversation_and_inbound(client: AsyncClient, webhook: str) -> None:
    ctx, base, entry = await setup(client)
    h = ctx["headers"]
    url = f"{base}/feedback/{entry['id']}/sms"
    whatsapp = webhook.replace("/sms/", "/whatsapp/")

    r = await client.post(url, headers=h, json={"body": "Bonjour", "channel": "whatsapp"})
    assert r.status_code == 201 and r.json()["channel"] == "whatsapp"
    # Réponse par WhatsApp : même échange, canal conservé.
    r = await client.post(whatsapp, data={"from": "whatsapp:+243990000001", "text": "Merci"})
    assert r.status_code == 204
    thread = (await client.get(url, headers=h)).json()
    assert [(m["channel"], m["direction"]) for m in thread] == [
        ("whatsapp", "outbound"),
        ("whatsapp", "inbound"),
    ]
    assert thread[1]["phone"] == "+243990000001"

    # Nouveau retour reçu par WhatsApp grâce au code du projet.
    r = await client.post(whatsapp, json={"from": "+243820000000", "text": "KIW Pas d'eau"})
    assert r.status_code == 204
    entries = (await client.get(f"{base}/feedback", headers=h)).json()
    assert any(e["description"] == "Pas d'eau" and e["channel"] == "sms" for e in entries)

    r = await client.post(
        f"{url}/simulate", headers=h, json={"body": "Encore moi", "channel": "whatsapp"}
    )
    assert r.status_code == 201 and r.json()["channel"] == "whatsapp"


async def test_meta_whatsapp_webhook(
    client: AsyncClient, webhook: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx, base, _ = await setup(client)
    settings = get_settings()
    monkeypatch.setattr(settings, "whatsapp_provider", "meta")
    monkeypatch.setattr(settings, "meta_whatsapp_token", "jeton")
    monkeypatch.setattr(settings, "meta_whatsapp_phone_number_id", "123")
    monkeypatch.setattr(settings, "meta_app_secret", "secret-app")
    whatsapp = webhook.replace("/sms/", "/whatsapp/")

    params = {"hub.mode": "subscribe", "hub.verify_token": "secret-de-test", "hub.challenge": "42"}
    r = await client.get(whatsapp, params=params)
    assert r.status_code == 200 and r.text == "42"
    params["hub.verify_token"] = "autre"
    assert (await client.get(whatsapp, params=params)).status_code == 403

    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "243830000000",
                                    "id": "wamid.1",
                                    "type": "text",
                                    "text": {"body": "KIW La latrine est cassée"},
                                },
                                {"from": "243830000000", "id": "wamid.2", "type": "image"},
                            ]
                        }
                    }
                ]
            }
        ]
    }
    raw = json.dumps(payload).encode()
    headers = {"content-type": "application/json"}
    bad = await client.post(
        whatsapp, content=raw, headers={**headers, "x-hub-signature-256": "sha256=0"}
    )
    assert bad.status_code == 403
    signature = "sha256=" + hmac.new(b"secret-app", raw, hashlib.sha256).hexdigest()
    r = await client.post(
        whatsapp, content=raw, headers={**headers, "x-hub-signature-256": signature}
    )
    assert r.status_code == 204
    entries = (await client.get(f"{base}/feedback", headers=ctx["headers"])).json()
    created = next(e for e in entries if e["description"] == "La latrine est cassée")
    assert created["contact"] == "+243830000000"


async def test_whatsapp_adapters() -> None:
    sent: dict[str, Any] = {}

    def twilio(request: httpx.Request) -> httpx.Response:
        sent["form"] = dict(httpx.QueryParams(request.content.decode()))
        return httpx.Response(201, json={"sid": "SM1"})

    gateway = sms.TwilioGateway(
        "AC1", "tok", "+14155238886", httpx.MockTransport(twilio), whatsapp=True
    )
    await gateway.send("+243990000001", "Bonjour")
    assert sent["form"]["To"] == "whatsapp:+243990000001"
    assert sent["form"]["From"] == "whatsapp:+14155238886"
    [inbound] = gateway.parse_inbound({"From": "whatsapp:+243990000001", "Body": "Oui"})
    assert inbound.phone == "+243990000001"

    def meta(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/123/messages")
        assert request.headers["Authorization"] == "Bearer jeton"
        sent["json"] = json.loads(request.content)
        return httpx.Response(200, json={"messages": [{"id": "wamid.9"}]})

    meta_gateway = sms.MetaWhatsAppGateway("jeton", "123", transport=httpx.MockTransport(meta))
    assert (await meta_gateway.send("+243990000001", "Salut")).provider_message_id == "wamid.9"
    assert sent["json"]["to"] == "243990000001" and sent["json"]["text"] == {"body": "Salut"}

    with pytest.raises(sms.SmsError, match="TWILIO_WHATSAPP_SENDER"):
        sms.get_gateway(Settings(whatsapp_provider="twilio"), "whatsapp")
