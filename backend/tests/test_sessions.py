import inspect
import secrets
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from app.core import crypto
from app.core.config import get_settings
from app.models import UserSession
from app.services import sessions
from tests.conftest import owner_engine, register
from tests.test_organizations import add_member, login

AUTH = "/api/v1/auth"


# Mot de passe des comptes créés par register() et add_member() : repris de conftest plutôt que
# recopié, pour qu'aucun mot de passe en clair ne figure dans ce fichier.
PASSWORD = inspect.signature(register).parameters["password"].default


def bearer(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def test_logout_revokes_tokens(client: AsyncClient) -> None:
    ctx = await register(client, "a@example.org")
    tokens = ctx["tokens"]
    assert (await client.get(f"{AUTH}/me", headers=ctx["headers"])).status_code == 200
    assert (await client.post(f"{AUTH}/logout", headers=ctx["headers"])).status_code == 204
    # Le jeton d'accès et le jeton de rafraîchissement ne valent plus rien.
    assert (await client.get(f"{AUTH}/me", headers=ctx["headers"])).status_code == 401
    r = await client.post(f"{AUTH}/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 401


async def test_refresh_rotates_and_detects_reuse(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = await register(client, "a@example.org")
    first = ctx["tokens"]["refresh_token"]
    r = await client.post(f"{AUTH}/refresh", json={"refresh_token": first})
    assert r.status_code == 200
    second = r.json()["refresh_token"]
    assert second != first
    # Deux onglets qui rafraîchissent en même temps : le jeton tout juste remplacé passe encore.
    assert (await client.post(f"{AUTH}/refresh", json={"refresh_token": first})).status_code == 200

    # Passé le délai de grâce, rejouer un jeton remplacé ferme la session.
    monkeypatch.setattr(sessions, "ROTATION_GRACE", timedelta(0))
    third = (await client.post(f"{AUTH}/refresh", json={"refresh_token": second})).json()
    assert (await client.post(f"{AUTH}/refresh", json={"refresh_token": first})).status_code == 401
    assert (await client.get(f"{AUTH}/me", headers=bearer(third))).status_code == 401


async def test_expired_session_is_refused(client: AsyncClient) -> None:
    ctx = await register(client, "a@example.org")
    async with owner_engine.begin() as conn:
        await conn.execute(
            update(UserSession).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    assert (await client.get(f"{AUTH}/me", headers=ctx["headers"])).status_code == 401


async def test_change_password_closes_other_sessions(client: AsyncClient) -> None:
    ctx = await register(client, "a@example.org")
    other = await login(client, "a@example.org")
    sessions_list = (await client.get(f"{AUTH}/sessions", headers=ctx["headers"])).json()
    assert len(sessions_list) == 2 and sum(s["current"] for s in sessions_list) == 1

    new = secrets.token_urlsafe(12)
    body = {"current_password": secrets.token_urlsafe(12), "new_password": new}
    r = await client.post(f"{AUTH}/password", headers=ctx["headers"], json=body)
    assert r.status_code == 422
    body["current_password"] = PASSWORD
    r = await client.post(f"{AUTH}/password", headers=ctx["headers"], json=body)
    assert r.status_code == 204
    assert (await client.get(f"{AUTH}/me", headers=ctx["headers"])).status_code == 200
    assert (await client.get(f"{AUTH}/me", headers=other)).status_code == 401
    r = await client.post(f"{AUTH}/login", json={"email": "a@example.org", "password": new})
    assert r.status_code == 200

    assert (await client.post(f"{AUTH}/logout-all", headers=ctx["headers"])).status_code == 204
    assert (await client.get(f"{AUTH}/me", headers=ctx["headers"])).status_code == 401


async def test_initial_password_and_reset_link(client: AsyncClient) -> None:
    ctx = await register(client, "admin@example.org")
    member = await add_member(client, ctx, "agent@example.org", "field_agent")
    r = await client.post(
        f"{AUTH}/login", json={"email": "agent@example.org", "password": PASSWORD}
    )
    assert r.json()["must_change_password"] is True
    agent = bearer(r.json())
    assert (await client.get(f"{AUTH}/me", headers=agent)).json()["must_change_password"] is True

    url = f"/api/v1/orgs/{ctx['org_id']}/members/{member['id']}/reset-link"
    assert (await client.post(url, headers=agent)).status_code == 403
    link = (await client.post(url, headers=ctx["headers"])).json()
    token = link["path"].split("token=")[1]

    reset = {"token": token, "new_password": secrets.token_urlsafe(12)}
    r = await client.post(f"{AUTH}/password/reset", json=reset)
    assert r.status_code == 200 and r.json()["must_change_password"] is False
    # Usage unique, et les anciennes sessions sont fermées.
    assert (await client.post(f"{AUTH}/password/reset", json=reset)).status_code == 422
    assert (await client.get(f"{AUTH}/me", headers=agent)).status_code == 401

    # Membre d'un autre espace : l'administrateur ne peut pas créer de lien pour lui.
    other = await register(client, "other@example.org", org="Autre")
    r = await client.post(
        f"/api/v1/orgs/{other['org_id']}/members",
        headers=other["headers"],
        json={"email": "agent@example.org", "role": "viewer"},
    )
    assert r.status_code == 201
    assert (await client.post(url, headers=ctx["headers"])).status_code == 409


async def test_forgot_password_sends_email(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await register(client, "a@example.org")
    sent: list[tuple[str, str]] = []

    async def fake_send(to: str, subject: str, body: str) -> bool:
        sent.append((to, body))
        return True

    from app.services import mailer

    monkeypatch.setattr(mailer, "send", fake_send)
    # Sans SMTP, rien ne part ; la réponse est la même que l'adresse existe ou non.
    assert (
        await client.post(f"{AUTH}/password/forgot", json={"email": "a@example.org"})
    ).status_code == 204
    assert sent == []
    monkeypatch.setattr(get_settings(), "smtp_host", "smtp.example.org")
    for email in ("a@example.org", "inconnu@example.org"):
        r = await client.post(f"{AUTH}/password/forgot", json={"email": email})
        assert r.status_code == 204
    assert [to for to, _ in sent] == ["a@example.org"]
    token = sent[0][1].split("token=")[1].split()[0]
    r = await client.post(
        f"{AUTH}/password/reset", json={"token": token, "new_password": secrets.token_urlsafe(12)}
    )
    assert r.status_code == 200


async def test_two_factor_login(client: AsyncClient) -> None:
    ctx = await register(client, "a@example.org")
    h = ctx["headers"]
    assert (await client.get(f"{AUTH}/me", headers=h)).json()["mfa_recommended"] is True
    setup = (await client.post(f"{AUTH}/totp/setup", headers=h)).json()
    assert setup["uri"].startswith("otpauth://totp/") and setup["qr_svg"].startswith(
        "data:image/svg"
    )
    secret = setup["secret"]
    bad = await client.post(f"{AUTH}/totp/enable", headers=h, json={"code": "000000"})
    assert bad.status_code == 422 or crypto.totp_now(secret) == "000000"
    r = await client.post(f"{AUTH}/totp/enable", headers=h, json={"code": crypto.totp_now(secret)})
    assert r.status_code == 204
    me = (await client.get(f"{AUTH}/me", headers=h)).json()
    assert me["totp_enabled"] is True and me["mfa_recommended"] is False

    creds = {"email": "a@example.org", "password": PASSWORD}
    r = await client.post(f"{AUTH}/login", json=creds)
    assert r.status_code == 401 and r.headers["x-otp-required"] == "1"
    r = await client.post(f"{AUTH}/login", json={**creds, "otp": crypto.totp_now(secret)})
    assert r.status_code == 200

    r = await client.post(f"{AUTH}/totp/disable", headers=h, json={"code": crypto.totp_now(secret)})
    assert r.status_code == 204
    assert (await client.post(f"{AUTH}/login", json=creds)).status_code == 200


def test_totp_rfc_vector() -> None:
    import base64

    secret = base64.b32encode(b"12345678901234567890").decode()
    assert crypto.totp_now(secret, at=59) == "287082"
    assert crypto.verify_totp(secret, "287082", at=59 + 30)
    assert not crypto.verify_totp(secret, "287082", at=59 + 90)
