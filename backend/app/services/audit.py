from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


def record(
    session: AsyncSession,
    *,
    organization_id: UUID,
    actor_id: UUID | None,
    action: str,
    entity_type: str,
    entity_id: UUID | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    """Ajoute une entrée d'audit dans la transaction en cours (validée avec elle)."""
    session.add(
        AuditLog(
            organization_id=organization_id,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            data=data or {},
        )
    )


# Une même consultation répétée (actualisation de la page) n'est inscrite qu'une fois par période.
ACCESS_WINDOW = timedelta(minutes=15)


async def record_access(
    session: AsyncSession,
    *,
    organization_id: UUID,
    actor_id: UUID | None,
    action: str,
    entity_type: str,
    entity_id: UUID,
    data: dict[str, Any] | None = None,
) -> None:
    """Inscrit la consultation de données personnelles (plainte sensible, contact, échanges,
    photo originale), sauf si la même personne a vu la même chose il y a moins de 15 minutes.
    """
    data = data or {}
    seen = await session.scalar(
        select(AuditLog.id)
        .where(
            AuditLog.organization_id == organization_id,
            AuditLog.actor_id == actor_id,
            AuditLog.action == action,
            AuditLog.entity_id == entity_id,
            AuditLog.data == data,
            AuditLog.created_at >= datetime.now(UTC) - ACCESS_WINDOW,
        )
        .limit(1)
    )
    if seen is None:
        record(
            session,
            organization_id=organization_id,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            data=data,
        )
