from httpx import AsyncClient

from tests.conftest import register


async def test_health(client: AsyncClient) -> None:
    assert (await client.get("/health")).json() == {"status": "ok"}


async def test_register_creates_user_and_admin_org(client: AsyncClient) -> None:
    ctx = await register(client, "Awa@Example.org", org="Solidarité Kivu")
    me = (await client.get("/api/v1/auth/me", headers=ctx["headers"])).json()
    assert me["email"] == "awa@example.org"
    assert me["organizations"][0]["name"] == "Solidarité Kivu"
    assert me["organizations"][0]["slug"] == "solidarite-kivu"
    assert me["organizations"][0]["role"] == "admin"


async def test_register_duplicate_email(client: AsyncClient) -> None:
    await register(client, "a@example.org")
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "A@example.org",
            "full_name": "A",
            "password": "motdepasse1",
            "organization_name": "Autre",
        },
    )
    assert r.status_code == 409


async def test_login_and_refresh(client: AsyncClient) -> None:
    await register(client, "b@example.org")
    bad = await client.post(
        "/api/v1/auth/login", json={"email": "b@example.org", "password": "mauvais-mdp"}
    )
    assert bad.status_code == 401
    ok = await client.post(
        "/api/v1/auth/login", json={"email": "B@example.org", "password": "motdepasse1"}
    )
    assert ok.status_code == 200
    refreshed = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": ok.json()["refresh_token"]}
    )
    assert refreshed.status_code == 200
    # Un jeton d'accès ne peut pas servir de jeton de rafraîchissement, et inversement.
    wrong = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": ok.json()["access_token"]}
    )
    assert wrong.status_code == 401
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {ok.json()['refresh_token']}"}
    )
    assert me.status_code == 401


async def test_me_requires_auth(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    r = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer nimportequoi"})
    assert r.status_code == 401
