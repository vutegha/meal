import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, MetaData, event, func, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, SessionTransaction, mapped_column

from app.core.config import get_settings

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class IdMixin:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# Montants (Decimal) et dates des colonnes JSONB : enregistrés en texte, relus par Pydantic.
engine = create_async_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    json_serializer=lambda value: json.dumps(value, default=str),
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


@event.listens_for(engine.sync_engine, "connect")
def _use_app_role(dbapi_connection: Any, _: Any) -> None:
    """Endosse le rôle applicatif, soumis à la Row Level Security (voir app/core/rls.py)."""
    role = get_settings().db_app_role
    if role:
        # Hors transaction, sinon le rollback du pool annulerait le changement de rôle. Sans
        # effet tant que la migration qui crée le rôle n'est pas passée.
        dbapi_connection.run_async(
            lambda conn: conn.fetch(
                "SELECT set_config('role', rolname, false) FROM pg_roles "
                "WHERE rolname = $1 AND pg_has_role(current_user, oid, 'MEMBER')",
                role,
            )
        )


_TENANT_SQL = text(
    "SELECT set_config('app.current_org', :org, true), set_config('app.system', :system, true)"
)


def _tenant_params(session: Session) -> dict[str, str]:
    return {
        "org": session.info.get("org_id", ""),
        "system": "on" if session.info.get("system") else "off",
    }


@event.listens_for(Session, "after_begin")
def _apply_tenant(session: Session, _: SessionTransaction, connection: Connection) -> None:
    """Chaque transaction reçoit l'organisation courante : les politiques RLS s'appuient dessus."""
    if session.info.get("org_id") or session.info.get("system"):
        connection.execute(_TENANT_SQL, _tenant_params(session))


async def bind_org(session: AsyncSession, org_id: UUID) -> None:
    """Limite la session à une organisation, y compris pour la transaction déjà ouverte."""
    session.info["org_id"] = str(org_id)
    session.info.pop("system", None)
    if session.in_transaction():
        await session.execute(_TENANT_SQL, _tenant_params(session.sync_session))


def system_session() -> AsyncSession:
    """Session des tâches internes (worker, démonstration) : voit toutes les organisations."""
    return SessionLocal(info={"system": True})


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
