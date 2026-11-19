from pathlib import Path

from httpx import AsyncClient

from app.core.config import get_settings
from tests.conftest import register
from tests.test_executions import execution_body, photo, setup
from tests.test_organizations import add_member, login


async def test_account_deletion_anonymizes_and_blocks_login(client: AsyncClient) -> None:
    ctx = await register(client, "admin@comptes.org", "ONG Comptes")
    member = await add_member(client, ctx, "agent@comptes.org", "field_agent")
    agent = await login(client, "agent@comptes.org")

    # Seul administrateur : il doit d'abord passer la main.
    r = await client.post(
        "/api/v1/auth/me/delete", headers=ctx["headers"], json={"password": "motdepasse1"}
    )
    assert r.status_code == 409 and "ONG Comptes" in r.json()["detail"]

    r = await client.post("/api/v1/auth/me/delete", headers=agent, json={"password": "mauvais"})
    assert r.status_code == 422
    r = await client.post("/api/v1/auth/me/delete", headers=agent, json={"password": "motdepasse1"})
    assert r.status_code == 204
    assert (await client.get("/api/v1/auth/me", headers=agent)).status_code == 401
    r = await client.post(
        "/api/v1/auth/login", json={"email": "agent@comptes.org", "password": "motdepasse1"}
    )
    assert r.status_code == 401

    members = await client.get(f"/api/v1/orgs/{ctx['org_id']}/members", headers=ctx["headers"])
    assert [m["user"]["email"] for m in members.json()] == ["admin@comptes.org"]
    audit = (await client.get(f"/api/v1/orgs/{ctx['org_id']}/audit", headers=ctx["headers"])).json()
    deleted = next(e for e in audit if e["action"] == "member.account_deleted")
    assert deleted["entity_id"] == member["id"] and "email" not in deleted["data"]
    # L'adresse est libérée : la personne peut revenir avec un nouveau compte.
    await register(client, "agent@comptes.org", "Nouvelle ONG")


async def test_closing_an_organization_erases_data_and_files(client: AsyncClient) -> None:
    ctx, base, nodes, _ = await setup(client)
    h = ctx["headers"]
    execution = (
        await client.post(
            f"{base}/executions",
            headers=h,
            json=execution_body(nodes["activity"]["id"]),
        )
    ).json()
    r = await client.post(
        f"{base}/executions/{execution['id']}/evidence",
        headers=h,
        files={"file": ("seance.jpg", photo(), "image/jpeg")},
    )
    assert r.status_code == 201, r.text
    folder = Path(get_settings().storage_local_path) / ctx["org_id"]
    assert any(folder.rglob("*.jpg"))

    url = f"/api/v1/orgs/{ctx['org_id']}/close"
    r = await client.post(url, headers=h, json={"name": "Autre", "password": "motdepasse1"})
    assert r.status_code == 422
    r = await client.post(url, headers=h, json={"name": "Org", "password": "mauvais"})
    assert r.status_code == 422
    other = (await client.post("/api/v1/orgs", headers=h, json={"name": "Seconde"})).json()
    r = await client.post(url, headers=h, json={"name": "Org", "password": "motdepasse1"})
    assert r.status_code == 204, r.text
    assert not folder.exists()
    assert (await client.get(f"/api/v1/orgs/{ctx['org_id']}", headers=h)).status_code in (403, 404)
    me = (await client.get("/api/v1/auth/me", headers=h)).json()
    assert [o["name"] for o in me["organizations"]] == ["Seconde"]

    # Dernier espace fermé, compte supprimé avec.
    r = await client.post(
        f"/api/v1/orgs/{other['id']}/close",
        headers=h,
        json={"name": "Seconde", "password": "motdepasse1", "delete_account": True},
    )
    assert r.status_code == 204, r.text
    assert (await client.get("/api/v1/auth/me", headers=h)).status_code == 401


async def test_local_storage_deletes_a_folder_only(tmp_path: Path) -> None:
    from app.documents.storage import LocalStorage

    storage = LocalStorage(str(tmp_path))
    await storage.put("org/projet/a.jpg", b"a", "image/jpeg")
    await storage.put("org/projet/b/c.pdf", b"c", "application/pdf")
    await storage.put("org/autre/d.jpg", b"d", "image/jpeg")
    assert await storage.delete_prefix("org/projet/") == 2
    assert await storage.get("org/autre/d.jpg") == b"d"
    assert await storage.delete_prefix("") == 0 and await storage.delete_prefix("/") == 0
    assert (tmp_path / "org/autre/d.jpg").exists()
