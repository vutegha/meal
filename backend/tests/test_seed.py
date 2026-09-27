from httpx import AsyncClient

from app.core.db import SessionLocal
from app.scripts.seed import DEMO_EMAIL, seed


async def test_seed_creates_usable_demo_project(client: AsyncClient) -> None:
    async with SessionLocal() as session:
        password = await seed(session)
    assert password
    async with SessionLocal() as session:
        assert await seed(session) is None  # idempotent

    tokens = (
        await client.post("/api/v1/auth/login", json={"email": DEMO_EMAIL, "password": password})
    ).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    org_id = (await client.get("/api/v1/orgs", headers=headers)).json()[0]["id"]
    projects = (await client.get(f"/api/v1/orgs/{org_id}/projects", headers=headers)).json()
    base = f"/api/v1/orgs/{org_id}/projects/{projects[0]['id']}"

    tree = (await client.get(f"{base}/logframe", headers=headers)).json()
    assert tree[0]["code"] == "OG"
    assert [o["code"] for o in tree[0]["children"]] == ["OS1", "OS2"]
    summary = (await client.get(f"{base}/budget/summary", headers=headers)).json()
    assert summary["planned"] == "68100.00"
    indicators = (await client.get(f"{base}/indicators", headers=headers)).json()
    assert {i["code"]: i["achieved"] for i in indicators}["I2"] == "390.0000"
