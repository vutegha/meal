"""Changement et réinitialisation des mots de passe."""

import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.crypto import token_hash
from app.core.security import hash_password
from app.models import PasswordReset, User
from app.services import sessions


async def set_password(
    session: AsyncSession, user: User, password: str, keep_session: UUID | None = None
) -> None:
    """Nouveau mot de passe : les autres sessions sont fermées, les liens en attente annulés."""
    user.password_hash = hash_password(password)
    user.must_change_password = False
    user.password_changed_at = datetime.now(UTC)
    await sessions.revoke_all(session, user.id, keep=keep_session)
    await session.execute(
        update(PasswordReset)
        .where(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None))
        .values(used_at=datetime.now(UTC))
    )


async def create_reset(
    session: AsyncSession, user: User, created_by: UUID | None
) -> tuple[str, datetime]:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(UTC) + timedelta(hours=get_settings().password_reset_hours)
    session.add(
        PasswordReset(
            user_id=user.id, token_hash=token_hash(token), expires_at=expires, created_by=created_by
        )
    )
    await session.flush()
    return token, expires


async def use_reset(session: AsyncSession, token: str) -> User | None:
    reset = await session.scalar(
        select(PasswordReset).where(PasswordReset.token_hash == token_hash(token)).with_for_update()
    )
    if reset is None or reset.used_at is not None or reset.expires_at <= datetime.now(UTC):
        return None
    reset.used_at = datetime.now(UTC)
    return await session.get(User, reset.user_id)


def reset_path(token: str) -> str:
    return f"/reset-password?token={token}"
