from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy import text

from app.scripts.platform_admin import main as grant
from tests.conftest import owner_engine, register
from tests.test_billing import billing_of, signup


async def platform_admin(client: AsyncClient) -> dict[str, Any]:
    ctx = await register(client, "ops@wemeal.org")
    assert await grant("ops@wemeal.org", revoke=False) == 0
    me = (await client.get("/api/v1/auth/me", headers=ctx["headers"])).json()
    assert me["is_platform_admin"] is True
    return ctx


async def test_admin_is_hidden_from_other_users(client: AsyncClient) -> None:
    ctx = await register(client, "user@x.org")
    me = (await client.get("/api/v1/auth/me", headers=ctx["headers"])).json()
    assert me["is_platform_admin"] is False
    r = await client.get("/api/v1/admin/subscriptions", headers=ctx["headers"])
    assert r.status_code == 404
    r = await client.patch(
        f"/api/v1/admin/subscriptions/{ctx['org_id']}",
        headers=ctx["headers"],
        json={"plan": "institution"},
    )
    assert r.status_code == 404
    assert (await client.get("/api/v1/admin/subscriptions")).status_code == 401


async def test_admin_lists_every_organization(client: AsyncClient) -> None:
    admin = await platform_admin(client)
    solo = await signup(client, "solo@x.org", account_type="individual", cycle="usage")
    team = await register(client, "team@x.org")
    await client.post(
        f"/api/v1/orgs/{team['org_id']}/billing/checkout",
        headers=team["headers"],
        json={"plan": "team", "cycle": "annual"},
    )

    r = await client.get("/api/v1/admin/subscriptions", headers=admin["headers"])
    assert r.status_code == 200, r.text
    data = r.json()
    rows = {row["organization_id"]: row for row in data["items"]}
    assert len(rows) == 3
    assert rows[solo["org_id"]]["contact_email"] == "solo@x.org"
    assert (rows[solo["org_id"]]["plan"], rows[solo["org_id"]]["credits"]) == ("solo", 5)
    assert rows[team["org_id"]]["status"] == "active"
    assert rows[team["org_id"]]["total_paid"] == "590.00"
    summary = data["summary"]
    assert summary["organizations"] == 3
    assert summary["by_status"] == {"trialing": 1, "active": 2, "canceled": 0, "expired": 0}
    assert summary["monthly_recurring"] == "49.17"
    assert summary["revenue_last_30_days"] == "590.00"

    r = await client.get(
        "/api/v1/admin/subscriptions", headers=admin["headers"], params={"q": "SOLO@"}
    )
    assert [row["organization_id"] for row in r.json()["items"]] == [solo["org_id"]]
    r = await client.get(
        "/api/v1/admin/subscriptions", headers=admin["headers"], params={"status": "trialing"}
    )
    assert [row["organization_id"] for row in r.json()["items"]] == [admin["org_id"]]
    assert r.json()["summary"]["organizations"] == 3


async def test_admin_updates_a_subscription(client: AsyncClient) -> None:
    admin = await platform_admin(client)
    team = await register(client, "late@x.org")
    async with owner_engine.begin() as conn:
        await conn.execute(
            text("UPDATE subscriptions SET trial_ends_at = :end WHERE organization_id = :org"),
            {"end": datetime.now(UTC) - timedelta(days=3), "org": team["org_id"]},
        )
    assert (await billing_of(client, team))["status"] == "expired"
    url = f"/api/v1/admin/subscriptions/{team['org_id']}"

    # Paiement reçu hors ligne : Institution active pour un an.
    r = await client.patch(
        url,
        headers=admin["headers"],
        json={"plan": "institution", "cycle": "annual", "status": "active", "note": "Virement"},
    )
    assert r.status_code == 200, r.text
    row = r.json()
    assert (row["plan"], row["cycle"], row["status"]) == ("institution", "annual", "active")
    end = datetime.fromisoformat(row["current_period_end"])
    assert timedelta(days=364) < end - datetime.now(UTC) <= timedelta(days=365)
    me = (await client.get("/api/v1/auth/me", headers=team["headers"])).json()
    assert "messaging" in me["organizations"][0]["features"]

    r = await client.patch(url, headers=admin["headers"], json={"extend_days": 30})
    assert datetime.fromisoformat(r.json()["current_period_end"]) - end == timedelta(days=30)

    r = await client.patch(
        url, headers=admin["headers"], json={"cycle": "usage", "add_credits": 40}
    )
    assert (r.json()["status"], r.json()["credits"]) == ("active", 40)
    r = await client.patch(url, headers=admin["headers"], json={"add_credits": -100})
    assert r.json()["credits"] == 0

    # Une formule individuelle n'accueille qu'une personne.
    await client.post(
        f"/api/v1/orgs/{team['org_id']}/members",
        headers=team["headers"],
        json={
            "email": "second@x.org",
            "role": "viewer",
            "full_name": "Second",
            "initial_password": "motdepasse1",
        },
    )
    r = await client.patch(url, headers=admin["headers"], json={"plan": "solo"})
    assert r.status_code == 409
    r = await client.patch(
        "/api/v1/admin/subscriptions/00000000-0000-0000-0000-000000000000",
        headers=admin["headers"],
        json={"plan": "team"},
    )
    assert r.status_code == 404

    # Les changements apparaissent dans le journal de l'espace.
    audit = await client.get(f"/api/v1/orgs/{team['org_id']}/audit", headers=team["headers"])
    entries = [e for e in audit.json() if e["action"] == "subscription.admin_updated"]
    assert len(entries) == 4
    first = entries[-1]
    assert first["data"]["before"]["plan"] == "team"
    assert first["data"]["after"]["plan"] == "institution"
    assert first["data"]["note"] == "Virement"
