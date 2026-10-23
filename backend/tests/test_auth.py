import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from tests.conftest import register


async def test_health(client: AsyncClient) -> None:
    assert (await client.get("/health")).json() == {"status": "ok"}
    ready = await client.get("/health/ready")
    assert ready.status_code == 200 and ready.json()["database"] == "ok"


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


async def test_login_attempts_are_limited(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await register(client, "c@example.org")
    url = "/api/v1/auth/login"
    wrong = {"email": "c@example.org", "password": "mauvais-mdp"}
    good = {"email": "c@example.org", "password": "motdepasse1"}

    # Une réussite remet le compteur de l'adresse à zéro.
    for _ in range(4):
        assert (await client.post(url, json=wrong)).status_code == 401
    assert (await client.post(url, json=good)).status_code == 200
    for _ in range(5):
        assert (await client.post(url, json=wrong)).status_code == 401
    # Cinq échecs : même le bon mot de passe est refusé jusqu'à la fin de la fenêtre.
    r = await client.post(url, json=good)
    assert r.status_code == 429 and r.headers["retry-after"] == "900"

    # Compteur par adresse IP : une autre adresse e-mail ne contourne pas la limite.
    monkeypatch.setattr(get_settings(), "login_max_failures_per_ip", 11)
    for i in range(2):
        other = {"email": f"inconnu{i}@example.org", "password": "x"}
        assert (await client.post(url, json=other)).status_code == 401
    assert (await client.post(url, json=other)).status_code == 429

    assert (await client.post(url, json={**good, "password": "x" * 129})).status_code == 422


def test_weak_secret_key_refused_in_production() -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(environment="production", secret_key="remplacer-par-une-longue-valeur-aleatoire")
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(environment="production", secret_key="trop-courte")
    Settings(environment="production", secret_key="x" * 48)
    Settings(environment="development", secret_key="change-me-in-production")
