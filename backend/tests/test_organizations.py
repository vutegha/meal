from typing import Any

from httpx import AsyncClient

from tests.conftest import register


async def add_member(client: AsyncClient, ctx: dict[str, Any], email: str, role: str) -> Any:
    r = await client.post(
        f"/api/v1/orgs/{ctx['org_id']}/members",
        headers=ctx["headers"],
        json={
            "email": email,
            "role": role,
            "full_name": "Agent",
            "initial_password": "motdepasse1",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


async def login(client: AsyncClient, email: str) -> dict[str, str]:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": "motdepasse1"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_create_and_list_organizations(client: AsyncClient) -> None:
    ctx = await register(client, "a@example.org", org="Zeta")
    r = await client.post("/api/v1/orgs", headers=ctx["headers"], json={"name": "Alpha"})
    assert r.status_code == 201
    assert r.json()["role"] == "admin"
    orgs = (await client.get("/api/v1/orgs", headers=ctx["headers"])).json()
    assert [o["name"] for o in orgs] == ["Alpha", "Zeta"]


async def test_duplicate_names_get_unique_slugs(client: AsyncClient) -> None:
    a = await register(client, "a@example.org", org="Même Nom")
    b = await register(client, "b@example.org", org="Même Nom")
    slug_a = (await client.get(f"/api/v1/orgs/{a['org_id']}", headers=a["headers"])).json()
    slug_b = (await client.get(f"/api/v1/orgs/{b['org_id']}", headers=b["headers"])).json()
    assert slug_a["slug"] == "meme-nom"
    assert slug_b["slug"].startswith("meme-nom-")


async def test_member_management_and_roles(client: AsyncClient) -> None:
    admin = await register(client, "admin@example.org")
    member = await add_member(client, admin, "terrain@example.org", "field_agent")
    field_headers = await login(client, "terrain@example.org")
    org_url = f"/api/v1/orgs/{admin['org_id']}"

    # Un agent terrain voit l'organisation et ses membres…
    assert (await client.get(org_url, headers=field_headers)).json()["role"] == "field_agent"
    members = (await client.get(f"{org_url}/members", headers=field_headers)).json()
    assert {m["user"]["email"] for m in members} == {"admin@example.org", "terrain@example.org"}
    # …mais ne peut ni modifier l'organisation, ni gérer les membres, ni lire l'audit.
    assert (
        await client.patch(org_url, headers=field_headers, json={"name": "Piratée"})
    ).status_code == 403
    assert (
        await client.post(
            f"{org_url}/members",
            headers=field_headers,
            json={"email": "x@example.org", "role": "admin"},
        )
    ).status_code == 403
    assert (await client.get(f"{org_url}/audit", headers=field_headers)).status_code == 403

    # L'administrateur change le rôle puis retire le membre.
    r = await client.patch(
        f"{org_url}/members/{member['id']}", headers=admin["headers"], json={"role": "meal_officer"}
    )
    assert r.json()["role"] == "meal_officer"
    dup = await client.post(
        f"{org_url}/members",
        headers=admin["headers"],
        json={"email": "terrain@example.org", "role": "viewer"},
    )
    assert dup.status_code == 409
    r = await client.delete(f"{org_url}/members/{member['id']}", headers=admin["headers"])
    assert r.status_code == 204
    assert (await client.get(org_url, headers=field_headers)).status_code == 404

    actions = [
        e["action"] for e in (await client.get(f"{org_url}/audit", headers=admin["headers"])).json()
    ]
    assert set(actions) == {
        "organization.created",
        "member.added",
        "member.role_changed",
        "member.removed",
    }


async def test_new_member_requires_name_and_password(client: AsyncClient) -> None:
    admin = await register(client, "admin@example.org")
    r = await client.post(
        f"/api/v1/orgs/{admin['org_id']}/members",
        headers=admin["headers"],
        json={"email": "nouveau@example.org", "role": "viewer"},
    )
    assert r.status_code == 422


async def test_existing_user_can_join_another_org(client: AsyncClient) -> None:
    a = await register(client, "a@example.org", org="Org A")
    b = await register(client, "b@example.org", org="Org B")
    r = await client.post(
        f"/api/v1/orgs/{b['org_id']}/members",
        headers=b["headers"],
        json={"email": "a@example.org", "role": "viewer"},
    )
    assert r.status_code == 201
    orgs = (await client.get("/api/v1/orgs", headers=a["headers"])).json()
    assert {(o["name"], o["role"]) for o in orgs} == {("Org A", "admin"), ("Org B", "viewer")}


async def test_last_admin_cannot_be_removed_or_demoted(client: AsyncClient) -> None:
    admin = await register(client, "admin@example.org")
    org_url = f"/api/v1/orgs/{admin['org_id']}"
    me = (await client.get(f"{org_url}/members", headers=admin["headers"])).json()[0]
    r = await client.patch(
        f"{org_url}/members/{me['id']}", headers=admin["headers"], json={"role": "viewer"}
    )
    assert r.status_code == 409
    r = await client.delete(f"{org_url}/members/{me['id']}", headers=admin["headers"])
    assert r.status_code == 409


async def test_organizations_are_isolated(client: AsyncClient) -> None:
    a = await register(client, "a@example.org", org="Org A")
    b = await register(client, "b@example.org", org="Org B")
    b_member = await add_member(client, b, "agent-b@example.org", "field_agent")
    org_b = f"/api/v1/orgs/{b['org_id']}"

    # L'admin de A ne voit ni ne modifie rien dans B : 404 partout.
    assert (await client.get(org_b, headers=a["headers"])).status_code == 404
    assert (await client.get(f"{org_b}/members", headers=a["headers"])).status_code == 404
    assert (await client.get(f"{org_b}/audit", headers=a["headers"])).status_code == 404
    assert (await client.patch(org_b, headers=a["headers"], json={"name": "X"})).status_code == 404
    assert (
        await client.delete(f"{org_b}/members/{b_member['id']}", headers=a["headers"])
    ).status_code == 404

    # Un membre de B ne peut pas être manipulé via l'organisation A.
    org_a = f"/api/v1/orgs/{a['org_id']}"
    r = await client.patch(
        f"{org_a}/members/{b_member['id']}", headers=a["headers"], json={"role": "admin"}
    )
    assert r.status_code == 404
    r = await client.delete(f"{org_a}/members/{b_member['id']}", headers=a["headers"])
    assert r.status_code == 404

    # A ne voit que son organisation.
    orgs = (await client.get("/api/v1/orgs", headers=a["headers"])).json()
    assert [o["name"] for o in orgs] == ["Org A"]
