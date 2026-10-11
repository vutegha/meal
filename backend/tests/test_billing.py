from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from httpx import AsyncClient
from sqlalchemy import text

from app.core.db import SessionLocal
from app.services import billing
from tests.conftest import owner_engine, register
from tests.test_projects import create_project


async def signup(client: AsyncClient, email: str, **extra: Any) -> dict[str, Any]:
    body = {"email": email, "full_name": "Awa Kahindo", "password": "motdepasse1", **extra}
    r = await client.post("/api/v1/auth/register", json=body)
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    org = me["organizations"][0]
    return {"headers": headers, "org_id": org["id"], "org": org}


async def billing_of(client: AsyncClient, ctx: dict[str, Any]) -> dict[str, Any]:
    r = await client.get(f"/api/v1/orgs/{ctx['org_id']}/billing", headers=ctx["headers"])
    assert r.status_code == 200, r.text
    return dict(r.json())


async def set_subscription(org_id: str, **values: Any) -> None:
    columns = ", ".join(f"{k} = :{k}" for k in values)
    async with owner_engine.begin() as conn:
        await conn.execute(
            text(f"UPDATE subscriptions SET {columns} WHERE organization_id = :org"),
            {**values, "org": org_id},
        )


async def test_catalog_is_public(client: AsyncClient) -> None:
    r = await client.get("/api/v1/billing/plans")
    assert r.status_code == 200
    catalog = r.json()
    plans = {p["id"]: p for p in catalog["plans"]}
    assert plans["solo"]["account_type"] == "individual"
    assert "team" not in plans["solo"]["features"]
    assert {"team", "templates", "org_lessons", "audit"} <= set(plans["team"]["features"])
    assert plans["institution"]["limits"]["projects"] is None
    assert Decimal(plans["team"]["prices"]["annual"]) < 12 * Decimal(
        plans["team"]["prices"]["monthly"]
    )
    assert catalog["credit_packs"] == list(billing.CREDIT_PACKS)


async def test_registration_validates_account_and_plan(client: AsyncClient) -> None:
    base = {"full_name": "Awa", "password": "motdepasse1"}
    r = await client.post(
        "/api/v1/auth/register", json={**base, "email": "a@x.org", "account_type": "organization"}
    )
    assert r.status_code == 422
    r = await client.post(
        "/api/v1/auth/register",
        json={**base, "email": "b@x.org", "account_type": "individual", "plan": "team"},
    )
    assert r.status_code == 422
    r = await client.post(
        "/api/v1/auth/register",
        json={**base, "email": "c@x.org", "account_type": "individual", "plan": "inconnue"},
    )
    assert r.status_code == 422


async def test_organization_starts_with_trial(client: AsyncClient) -> None:
    ctx = await register(client, "org@x.org")
    me = (await client.get("/api/v1/auth/me", headers=ctx["headers"])).json()
    org = me["organizations"][0]
    assert org["account_type"] == "organization"
    assert org["plan"] == "team"
    assert "templates" in org["features"]

    sub = await billing_of(client, ctx)
    assert sub["status"] == "trialing"
    assert sub["cycle"] == "monthly"
    trial_end = datetime.fromisoformat(sub["trial_ends_at"])
    assert timedelta(days=13) < trial_end - datetime.now(UTC) <= timedelta(days=14)
    assert sub["usage"] == {"projects": 0, "members": 1, "ai_month_cost_usd": "0"}


async def test_individual_account_has_no_team_features(client: AsyncClient) -> None:
    ctx = await signup(client, "solo@x.org", account_type="individual", cycle="annual")
    assert ctx["org"]["name"] == "Espace de Awa Kahindo"
    assert ctx["org"]["account_type"] == "individual"
    assert "team" not in ctx["org"]["features"]
    org_url = f"/api/v1/orgs/{ctx['org_id']}"

    r = await client.post(
        f"{org_url}/members",
        headers=ctx["headers"],
        json={
            "email": "collegue@x.org",
            "role": "viewer",
            "full_name": "Collègue",
            "initial_password": "motdepasse1",
        },
    )
    assert r.status_code == 402
    assert "comptes organisation" in r.json()["detail"]
    template = {"kind": "tor", "name": "Maison", "sections": [{"key": "a", "title": "A"}]}
    r = await client.post(f"{org_url}/templates", headers=ctx["headers"], json=template)
    assert r.status_code == 402
    assert (await client.get(f"{org_url}/lessons", headers=ctx["headers"])).status_code == 402
    assert (await client.get(f"{org_url}/audit", headers=ctx["headers"])).status_code == 402

    # Trois projets au plus
    for code in ("P1", "P2", "P3"):
        await create_project(client, ctx, code)
    r = await client.post(
        f"{org_url}/projects",
        headers=ctx["headers"],
        json={"code": "P4", "title": "Un de trop", "currency": "USD"},
    )
    assert r.status_code == 402
    assert "3 projets" in r.json()["detail"]


async def test_checkout_activates_and_extends(client: AsyncClient) -> None:
    ctx = await register(client, "pay@x.org")
    url = f"/api/v1/orgs/{ctx['org_id']}/billing"
    r = await client.post(
        f"{url}/checkout", headers=ctx["headers"], json={"plan": "institution", "cycle": "annual"}
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["payment"]["amount"] == "2490.00"
    assert out["payment"]["provider"] == "simulation"
    assert out["payment"]["reference"].startswith("SIM-")
    sub = out["subscription"]
    assert (sub["plan"], sub["cycle"], sub["status"]) == ("institution", "annual", "active")
    assert sub["trial_ends_at"] is None
    first_end = datetime.fromisoformat(sub["current_period_end"])
    assert timedelta(days=364) < first_end - datetime.now(UTC) <= timedelta(days=365)

    # Renouveler la même formule prolonge la période en cours
    r = await client.post(
        f"{url}/checkout", headers=ctx["headers"], json={"plan": "institution", "cycle": "annual"}
    )
    second_end = datetime.fromisoformat(r.json()["subscription"]["current_period_end"])
    assert second_end - first_end == timedelta(days=365)

    payments = (await client.get(f"{url}/payments", headers=ctx["headers"])).json()
    assert len(payments) == 2

    r = await client.post(f"{url}/cancel", headers=ctx["headers"])
    assert r.json()["status"] == "canceled"
    assert r.json()["cancel_at_period_end"] is True

    # Seul un administrateur paie
    await client.post(
        f"/api/v1/orgs/{ctx['org_id']}/members",
        headers=ctx["headers"],
        json={
            "email": "viewer@x.org",
            "role": "viewer",
            "full_name": "Lecteur",
            "initial_password": "motdepasse1",
        },
    )
    viewer = await client.post(
        "/api/v1/auth/login", json={"email": "viewer@x.org", "password": "motdepasse1"}
    )
    viewer_headers = {"Authorization": f"Bearer {viewer.json()['access_token']}"}
    r = await client.post(
        f"{url}/checkout", headers=viewer_headers, json={"plan": "team", "cycle": "monthly"}
    )
    assert r.status_code == 403
    assert (await client.get(url, headers=viewer_headers)).status_code == 200

    # Passer à une formule individuelle exige de n'être plus qu'un membre
    r = await client.post(
        f"{url}/checkout", headers=ctx["headers"], json={"plan": "solo", "cycle": "monthly"}
    )
    assert r.status_code == 409


async def test_expired_subscription_blocks_new_work(client: AsyncClient) -> None:
    ctx = await register(client, "late@x.org")
    project_id = await create_project(client, ctx)
    await set_subscription(ctx["org_id"], trial_ends_at=datetime.now(UTC) - timedelta(days=1))

    assert (await billing_of(client, ctx))["status"] == "expired"
    r = await client.post(
        f"/api/v1/orgs/{ctx['org_id']}/projects",
        headers=ctx["headers"],
        json={"code": "P2", "title": "Nouveau", "currency": "USD"},
    )
    assert r.status_code == 402
    assert "expiré" in r.json()["detail"]
    # Les données restent consultables
    r = await client.get(
        f"/api/v1/orgs/{ctx['org_id']}/projects/{project_id}", headers=ctx["headers"]
    )
    assert r.status_code == 200
    async with SessionLocal() as session:
        reason = await billing.ai_block_reason(session, UUID(ctx["org_id"]), "logframe_extraction")
    assert reason and "expiré" in reason


async def test_usage_credits(client: AsyncClient) -> None:
    ctx = await signup(client, "usage@x.org", account_type="individual", cycle="usage")
    org_id = UUID(ctx["org_id"])
    sub = await billing_of(client, ctx)
    assert (sub["cycle"], sub["status"], sub["credits"]) == ("usage", "active", 5)

    r = await client.post(
        f"/api/v1/orgs/{org_id}/billing/checkout",
        headers=ctx["headers"],
        json={"plan": "solo", "cycle": "usage", "pack": 7},
    )
    assert r.status_code == 422
    r = await client.post(
        f"/api/v1/orgs/{org_id}/billing/checkout",
        headers=ctx["headers"],
        json={"plan": "solo", "cycle": "usage", "pack": 10},
    )
    assert r.json()["payment"]["amount"] == "20.00"
    assert r.json()["subscription"]["credits"] == 15

    await billing.spend_credit(org_id, "tor_generation")
    await billing.spend_credit(org_id, "document_ocr")  # inclus, non décompté
    assert (await billing_of(client, ctx))["credits"] == 14

    await set_subscription(str(org_id), credits=0)
    async with SessionLocal() as session:
        assert await billing.ai_block_reason(session, org_id, "tor_generation")
        assert await billing.ai_block_reason(session, org_id, "document_ocr") is None
        assert await billing.ai_cap(session, org_id) == Decimal("10")
