from httpx import AsyncClient

from app.scripts.revoke_sessions import main as revoke_sessions
from tests.conftest import register


async def test_revoke_sessions_closes_every_session(client: AsyncClient) -> None:
    first = await register(client, "un@securite.org")
    second = await register(client, "deux@securite.org")
    await revoke_sessions(["UN@securite.org"])
    assert (await client.get("/api/v1/auth/me", headers=first["headers"])).status_code == 401
    assert (await client.get("/api/v1/auth/me", headers=second["headers"])).status_code == 200
    await revoke_sessions([])
    assert (await client.get("/api/v1/auth/me", headers=second["headers"])).status_code == 401
