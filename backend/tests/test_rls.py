from typing import Any

from httpx import AsyncClient
from sqlalchemy import text

from app.core import rls
from app.core.db import SessionLocal, bind_org, engine, system_session
from tests.conftest import owner_engine, register
from tests.test_projects import create_project


async def test_every_tenant_table_has_rls() -> None:
    async with owner_engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT c.relname, c.relrowsecurity FROM pg_class c "
                "JOIN information_schema.columns col ON col.table_name = c.relname "
                "WHERE col.column_name = 'organization_id' AND col.table_schema = 'public' "
                "AND c.relkind = 'r'"
            )
        )
        tables: dict[str, bool] = {name: enabled for name, enabled in rows}
    assert set(tables) - {"memberships"} == set(rls.TENANT_TABLES)
    assert all(tables[t] for t in rls.TENANT_TABLES)
    assert not tables["memberships"]


async def test_api_connection_uses_app_role() -> None:
    async with engine.connect() as conn:
        assert (await conn.scalar(text("SELECT current_user"))) == rls.APP_ROLE


async def _setup(client: AsyncClient) -> tuple[dict[str, Any], dict[str, Any]]:
    a = await register(client, "a@rls.org", "Org A")
    b = await register(client, "b@rls.org", "Org B")
    await create_project(client, a, "PA")
    await create_project(client, b, "PB")
    return a, b


async def test_session_sees_only_its_org(client: AsyncClient) -> None:
    a, b = await _setup(client)
    count = text("SELECT count(*) FROM projects")
    async with SessionLocal() as session:
        # Sans organisation liée, rien n'est visible, même sans filtre dans la requête.
        assert await session.scalar(count) == 0
    async with SessionLocal() as session:
        await bind_org(session, a["org_id"])
        result = await session.execute(text("SELECT code FROM projects"))
        codes: list[str] = list(result.scalars())
        assert codes == ["PA"]
    async with system_session() as session:
        assert await session.scalar(count) == 2


async def test_cross_org_writes_are_rejected(client: AsyncClient) -> None:
    a, b = await _setup(client)
    async with SessionLocal() as session:
        await bind_org(session, a["org_id"])
        updated = await session.execute(
            text("UPDATE projects SET title = 'pirate' WHERE organization_id = :org"),
            {"org": b["org_id"]},
        )
        assert updated.rowcount == 0  # type: ignore[attr-defined]
        try:
            await session.execute(
                text(
                    "INSERT INTO lessons_learned (id, organization_id, project_id, title, "
                    "description, recommendation, tags, created_at) "
                    "SELECT gen_random_uuid(), :org, id, 't', '', '', '[]', now() FROM projects"
                ),
                {"org": b["org_id"]},
            )
        except Exception as exc:
            assert "row-level security" in str(exc)
        else:
            raise AssertionError("insertion dans une autre organisation acceptée")
