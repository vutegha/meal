"""Sessions de connexion : ouverture, rafraîchissement avec rotation, révocation."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import Claims, create_token
from app.models import User, UserSession
from app.schemas.auth import TokenPair

# Deux onglets peuvent rafraîchir en même temps avec le même jeton : le jeton tout juste
# remplacé reste accepté quelques secondes, sans être considéré comme volé.
ROTATION_GRACE = timedelta(seconds=60)


def tokens(user: User, record: UserSession) -> TokenPair:
    return TokenPair(
        access_token=create_token(user.id, "access", record.id),
        refresh_token=create_token(user.id, "refresh", record.id, record.generation),
        must_change_password=user.must_change_password,
    )


async def open_session(session: AsyncSession, user: User, user_agent: str = "") -> TokenPair:
    record = UserSession(
        user_id=user.id,
        expires_at=datetime.now(UTC) + timedelta(days=get_settings().refresh_token_days),
        user_agent=user_agent[:200],
    )
    session.add(record)
    await session.flush()
    return tokens(user, record)


async def is_active(session: AsyncSession, claims: Claims) -> bool:
    record = await session.get(UserSession, claims.session_id)
    return (
        record is not None
        and record.user_id == claims.user_id
        and record.revoked_at is None
        and record.expires_at > datetime.now(UTC)
    )


async def rotate(session: AsyncSession, user: User, claims: Claims) -> TokenPair | None:
    """Nouveau couple de jetons ; None si la session est close ou le jeton rejoué."""
    record = await session.get(UserSession, claims.session_id, with_for_update=True)
    now = datetime.now(UTC)
    if (
        record is None
        or record.user_id != user.id
        or record.revoked_at is not None
        or record.expires_at <= now
    ):
        return None
    if claims.generation == record.generation:
        record.generation += 1
        record.rotated_at = now
        # Une session active se prolonge : l'agent qui se connecte régulièrement reste connecté.
        record.expires_at = now + timedelta(days=get_settings().refresh_token_days)
        return tokens(user, record)
    recent = record.rotated_at is not None and now - record.rotated_at <= ROTATION_GRACE
    if claims.generation == record.generation - 1 and recent:
        return tokens(user, record)
    # Jeton ancien rejoué : quelqu'un d'autre le détient. La session est close pour tous.
    record.revoked_at = now
    return None


async def revoke(session: AsyncSession, session_id: UUID) -> None:
    await session.execute(
        update(UserSession)
        .where(UserSession.id == session_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


async def revoke_all(session: AsyncSession, user_id: UUID, keep: UUID | None = None) -> None:
    """Ferme toutes les sessions de la personne (sauf `keep`, celle en cours)."""
    query = update(UserSession).where(
        UserSession.user_id == user_id, UserSession.revoked_at.is_(None)
    )
    if keep is not None:
        query = query.where(UserSession.id != keep)
    await session.execute(query.values(revoked_at=datetime.now(UTC)))
