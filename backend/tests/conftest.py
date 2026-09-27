import os
import tempfile
from collections.abc import AsyncIterator
from typing import Any

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://meal:meal@localhost:5432/meal_test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-with-enough-length-0123456789")
os.environ["JOBS_INLINE"] = "true"
os.environ["STORAGE_LOCAL_PATH"] = tempfile.mkdtemp(prefix="wemeal-test-files-")

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core import rls
from app.core.config import get_settings
from app.core.db import Base, engine
from app.main import app

# Propriétaire des tables (sans changement de rôle) : schéma, RLS et nettoyage entre tests.
owner_engine = create_async_engine(get_settings().database_url)


@pytest.fixture(scope="session", autouse=True)
async def database() -> AsyncIterator[None]:
    async with owner_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        for enum_type in (
            "role",
            "project_status",
            "node_level",
            "aggregation",
            "document_status",
            "job_status",
            "proposal_status",
            "tor_status",
            "execution_status",
            "evidence_kind",
            "report_status",
            "periodic_kind",
            "feedback_channel",
            "feedback_category",
            "feedback_status",
        ):
            await conn.execute(text(f"DROP TYPE IF EXISTS {enum_type}"))
        await conn.run_sync(Base.metadata.create_all)
        for statement in rls.all_statements():
            await conn.execute(text(statement))
    await engine.dispose()
    yield
    await engine.dispose()
    await owner_engine.dispose()


@pytest.fixture(autouse=True)
async def clean_tables() -> AsyncIterator[None]:
    yield
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with owner_engine.begin() as conn:
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
