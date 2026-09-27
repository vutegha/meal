import os
from collections.abc import AsyncIterator
from typing import Any

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://meal:meal@localhost:5432/meal_test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-with-enough-length-0123456789")

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.db import Base, engine
from app.main import app


@pytest.fixture(scope="session", autouse=True)
async def database() -> AsyncIterator[None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.execute(text("DROP TYPE IF EXISTS role"))
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest.fixture(autouse=True)
async def clean_tables() -> AsyncIterator[None]:
    yield
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} CASCADE"))


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def register(
    client: AsyncClient, email: str, org: str = "Org", password: str = "motdepasse1"
) -> dict[str, Any]:
    """Inscrit un utilisateur et renvoie ses en-têtes et sa première organisation."""
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "full_name": email.split("@")[0],
            "password": password,
            "organization_name": org,
        },
    )
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    return {"headers": headers, "org_id": me["organizations"][0]["id"], "tokens": r.json()}
