import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, MetaData, event, func, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, SessionTransaction, mapped_column

from app.core.config import get_settings

logger = logging.getLogger(__name__)

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


_ROLE_SQL = text(
    "SELECT current_user, session_user, r.rolsuper, r.rolbypassrls, s.rolsuper "
    "FROM pg_roles r, pg_roles s WHERE r.rolname = current_user AND s.rolname = session_user"
)


async def role_problems() -> tuple[list[str], list[str]]:
    """Contrôle de démarrage : (problèmes bloquants, avertissements) sur le rôle de la base.

    Bloquant : la Row Level Security ne s'appliquerait pas (rôle applicatif absent, ou rôle qui
    contourne la RLS). Avertissement : connexion avec un superutilisateur, qui pourrait quitter le
    rôle applicatif (`RESET ROLE`) ; c'est la configuration des tests et du développement.
    """
    expected = get_settings().db_app_role
    if not expected:
        return [], ["DB_APP_ROLE vide : la Row Level Security ne s'applique pas"]
    async with engine.connect() as conn:
        row = (await conn.execute(_ROLE_SQL)).one()
    current, login, superuser, bypass, login_superuser = row
    blocking, warnings = [], []
    if current != expected:
        blocking.append(
            f"La connexion utilise le rôle {current} au lieu de {expected} : migrations non "
            "passées, ou compte de connexion qui n'est pas membre de ce rôle"
        )
    elif superuser or bypass:
        blocking.append(f"Le rôle {expected} contourne la Row Level Security")
    if login_superuser:
        warnings.append(
            f"Connexion à la base avec le superutilisateur {login} : utiliser un compte dédié "
            "(APP_DB_USER, voir app/scripts/db_login.py)"
        )
    return blocking, warnings


async def check_role() -> None:
    """Refuse de démarrer (API, worker) si la Row Level Security ne s'appliquerait pas."""
    blocking, warnings = await role_problems()
    for message in warnings:
        logger.warning(message)
    if blocking:
        raise RuntimeError("; ".join(blocking))


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


async def bind_system(session: AsyncSession) -> None:
    """Ouvre la session à toutes les organisations (administration de la plateforme)."""
    session.info["system"] = True
    session.info.pop("org_id", None)
    if session.in_transaction():
        await session.execute(_TENANT_SQL, _tenant_params(session.sync_session))


def system_session() -> AsyncSession:
    """Session des tâches internes (worker, démonstration) : voit toutes les organisations."""
    return SessionLocal(info={"system": True})


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
