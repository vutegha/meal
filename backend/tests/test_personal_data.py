from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.db import system_session
from app.models import AuditLog, FeedbackEntry, SmsMessage
from app.services.retention import ERASED, purge
from tests.conftest import owner_engine, register
from tests.test_organizations import add_member, login
from tests.test_projects import create_project


@pytest.fixture
def webhook(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(get_settings(), "sms_webhook_token", "secret-de-test")
    return "/api/v1/sms/inbound/secret-de-test"


async def test_find_export_and_erase_a_person(client: AsyncClient, webhook: str) -> None:
    ctx = await register(client, "admin@example.org")
    h = ctx["headers"]
    # Les SMS sont ouverts par la formule Institution.
    r = await client.post(
        f"/api/v1/orgs/{ctx['org_id']}/billing/checkout",
        headers=h,
        json={"plan": "institution", "cycle": "monthly"},
    )
    assert r.status_code == 200, r.text
    base = f"/api/v1/orgs/{ctx['org_id']}/projects/{await create_project(client, ctx, 'KIW')}"
    r = await client.post(
        f"{base}/feedback",
        headers=h,
        json={
            "channel": "hotline",
            "category": "complaint",
            "description": "Amina Kahindo n'a pas reçu son kit.",
            "contact": "+243 99 000-0001",
        },
    )
    entry = r.json()
    await client.post(f"{base}/feedback/{entry['id']}/sms", headers=h, json={"body": "Merci"})
    other = await client.post(
        f"{base}/feedback",
        headers=h,
        json={"channel": "hotline", "category": "information", "description": "Sans rapport"},
    )

    url = f"/api/v1/orgs/{ctx['org_id']}/personal-data"
    await add_member(client, ctx, "suivi@example.org", "meal_officer")
    officer = await login(client, "suivi@example.org")
    assert (await client.get(url, headers=officer, params={"q": "Amina"})).status_code == 403

    # Par le nom, ou par le numéro écrit autrement.
    for q in ("amina kahindo", "0990000001"):
        found = (await client.get(url, headers=h, params={"q": q})).json()
        assert [f["reference"] for f in found["feedback"]] == [entry["reference"]], q
    assert [m["body"] for m in found["feedback"][0]["messages"]] == ["Merci"]

    r = await client.post(
        f"{url}/erase",
        headers=h,
        json={"feedback_ids": [entry["id"]], "reason": "Demande de la personne"},
    )
    assert r.json() == {"feedback": 1, "submissions": 0}
    erased = (await client.get(f"{base}/feedback", headers=h)).json()
    erased_entry = next(e for e in erased if e["id"] == entry["id"])
    assert erased_entry["description"] == ERASED and erased_entry["contact"] == ""
    assert next(e for e in erased if e["id"] == other.json()["id"])["description"] == "Sans rapport"
    assert (await client.get(f"{base}/feedback/{entry['id']}/sms", headers=h)).json() == []
    assert (await client.get(url, headers=h, params={"q": "Amina"})).json()["feedback"] == []

    audit = (await client.get(f"/api/v1/orgs/{ctx['org_id']}/audit", headers=h)).json()
    erased_log = next(e for e in audit if e["action"] == "personal_data.erased")
    assert erased_log["data"]["reason"] == "Demande de la personne"
    searched = [e for e in audit if e["action"] == "personal_data.searched"]
    assert searched and "amina" not in str(searched).lower()


async def test_retention_purge(client: AsyncClient, webhook: str) -> None:
    ctx = await register(client, "admin@example.org")
    h = ctx["headers"]
    base = f"/api/v1/orgs/{ctx['org_id']}/projects/{await create_project(client, ctx, 'KIW')}"
    old = await client.post(
        f"{base}/feedback",
        headers=h,
        json={
            "channel": "hotline",
            "category": "complaint",
            "description": "Ancien",
            "contact": "1",
        },
    )
    recent = await client.post(
        f"{base}/feedback",
        headers=h,
        json={"channel": "hotline", "category": "complaint", "description": "Récent"},
    )
    for r in (old, recent):
        await client.patch(
            f"{base}/feedback/{r.json()['id']}",
            headers=h,
            json={"status": "closed", "response": "Traité"},
        )
    await client.post(webhook, data={"from": "+243810000009", "text": "inconnu"})
    async with owner_engine.begin() as conn:
        await conn.execute(
            update(FeedbackEntry)
            .where(FeedbackEntry.id == old.json()["id"])
            .values(closed_on=date.today() - timedelta(days=37 * 31))
        )
        await conn.execute(
            update(SmsMessage)
            .where(SmsMessage.organization_id.is_(None))
            .values(created_at=datetime.now(UTC) - timedelta(days=31))
        )

    async with system_session() as session:
        counts = await purge(session)
        await session.commit()
    assert counts["unmatched_sms"] == 1
    assert counts["feedback"] == {ctx["org_id"]: 1}

    entries = {e["id"]: e for e in (await client.get(f"{base}/feedback", headers=h)).json()}
    assert entries[old.json()["id"]]["description"] == ERASED
    assert entries[old.json()["id"]]["category"] == "complaint"  # statistiques préservées
    assert entries[recent.json()["id"]]["description"] == "Récent"
    async with system_session() as session:
        logged = await session.scalar(
            select(AuditLog).where(AuditLog.action == "feedback.anonymized")
        )
        assert logged is not None and logged.data["count"] == 1

    # Une seconde passe ne refait rien.
    async with system_session() as session:
        assert (await purge(session))["feedback"] == {}
