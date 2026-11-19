from httpx import AsyncClient

from tests.conftest import register
from tests.fake_llm import FakeLLM
from tests.test_executions import photo
from tests.test_organizations import add_member, login
from tests.test_projects import create_project
from tests.test_reports import generate, prepare
from tests.test_tor import fake_llm  # noqa: F401

__all__ = ["fake_llm"]


async def test_privacy_settings(client: AsyncClient) -> None:
    ctx = await register(client, "admin@example.org")
    url = f"/api/v1/orgs/{ctx['org_id']}/privacy"
    settings = (await client.get(url, headers=ctx["headers"])).json()
    assert settings == {
        "ai_enabled": True,
        "feedback_retention_months": 36,
        "sms_acknowledgement": True,
        "privacy_contact": "",
    }
    await add_member(client, ctx, "agent@example.org", "field_agent")
    agent = await login(client, "agent@example.org")
    assert (await client.patch(url, headers=agent, json={"ai_enabled": False})).status_code == 403
    r = await client.patch(
        url,
        headers=ctx["headers"],
        json={"ai_enabled": False, "privacy_contact": "dpo@ong.org"},
    )
    assert r.status_code == 200 and r.json()["ai_enabled"] is False
    audit = (await client.get(f"/api/v1/orgs/{ctx['org_id']}/audit", headers=ctx["headers"])).json()
    assert audit[0]["action"] == "organization.privacy_updated"


async def test_ai_can_be_disabled(client: AsyncClient, fake_llm: FakeLLM) -> None:
    ctx = await register(client, "admin@example.org")
    project_id = await create_project(client, ctx)
    org = f"/api/v1/orgs/{ctx['org_id']}"
    await client.patch(f"{org}/privacy", headers=ctx["headers"], json={"ai_enabled": False})
    r = await client.post(
        f"{org}/projects/{project_id}/feedback/classify",
        headers=ctx["headers"],
        json={"description": "Le relais demande de l'argent", "channel": "hotline"},
    )
    assert r.status_code >= 400 and "désactivée" in r.json()["detail"]
    assert fake_llm.calls == []


async def test_attendance_list_is_not_sent_to_ai(client: AsyncClient, fake_llm: FakeLLM) -> None:
    ctx, base, _, execution = await prepare(client)
    r = await client.post(
        f"{base}/executions/{execution}/evidence",
        headers=ctx["headers"],
        files={"file": ("presence.txt", b"Amina Kahindo +243990000001", "text/plain")},
        data={"kind": "attendance"},
    )
    assert r.status_code == 201, r.text
    await generate(client, ctx, base, execution)
    context = fake_llm.calls[0]["content"][0]["text"]
    assert "Amina Kahindo" not in context and "presence.txt" not in context
    assert 'type="minutes"' in context


async def test_consent_is_recorded(client: AsyncClient) -> None:
    ctx, base, _, execution = await prepare(client)
    url = f"{base}/executions/{execution}/evidence"
    r = await client.post(
        url,
        headers=ctx["headers"],
        files={"file": ("groupe.jpg", photo(), "image/jpeg")},
        data={"consent_given": "true", "consent_method": "written"},
    )
    evidence = r.json()
    assert evidence["consent_method"] == "written" and evidence["consent_recorded_at"]
    r = await client.patch(
        f"{base}/evidence/{evidence['id']}", headers=ctx["headers"], json={"consent_given": False}
    )
    assert r.json()["consent_method"] == "" and r.json()["consent_recorded_at"] is None
    r = await client.patch(
        f"{base}/evidence/{evidence['id']}",
        headers=ctx["headers"],
        json={"consent_given": True, "consent_method": "guardian"},
    )
    assert r.json()["consent_method"] == "guardian"
    bad = await client.patch(
        f"{base}/evidence/{evidence['id']}", headers=ctx["headers"], json={"consent_method": "x"}
    )
    assert bad.status_code == 422
