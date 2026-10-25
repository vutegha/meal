"""Crée ou met à jour le compte de connexion de l'API et du worker (APP_DB_USER).

Usage : `uv run python -m app.scripts.db_login`, après `alembic upgrade head`, avec le compte
propriétaire des tables (MIGRATION_DATABASE_URL). Docker Compose le lance à chaque démarrage
(service `migrate`).

Le compte n'est ni superutilisateur ni propriétaire des tables, et n'hérite d'aucun droit : il ne
peut rien lire tant qu'il n'a pas endossé le rôle `meal_app`, soumis à la Row Level Security.
Une connexion qui n'aurait pas changé de rôle échoue donc au lieu de tout voir.
"""

import asyncio

from sqlalchemy import String, bindparam, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings

ATTRIBUTES = "LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT"


async def main() -> None:
    settings = get_settings()
    user, password, role = settings.app_db_user, settings.app_db_password, settings.db_app_role
    if not password or not role:
        print("APP_DB_PASSWORD ou DB_APP_ROLE vide : compte de connexion non créé")
        return
    engine = create_async_engine(settings.migration_database_url or settings.database_url)
    async with engine.begin() as conn:
        if user == await conn.scalar(text("SELECT current_user")):
            raise SystemExit("APP_DB_USER doit différer du compte propriétaire des tables")
        # Mot de passe et nom cités par PostgreSQL lui-même (format %I et %L).
        statements = await conn.scalar(
            text(
                "SELECT format(CASE WHEN EXISTS (SELECT FROM pg_roles WHERE rolname = :user) "
                f"THEN 'ALTER ROLE %1$I {ATTRIBUTES} PASSWORD %2$L' "
                f"ELSE 'CREATE ROLE %1$I {ATTRIBUTES} PASSWORD %2$L' END, :user, :password)"
            ).bindparams(bindparam("user", type_=String), bindparam("password", type_=String)),
            {"user": user, "password": password},
        )
        await conn.exec_driver_sql(statements)
        grant = await conn.scalar(
            text("SELECT format('GRANT %I TO %I', CAST(:role AS text), CAST(:user AS text))"),
            {"role": role, "user": user},
        )
        await conn.exec_driver_sql(grant)
    await engine.dispose()
    print(f"Compte de connexion {user} prêt (rôle {role}, sans superutilisateur)")


if __name__ == "__main__":
    asyncio.run(main())
