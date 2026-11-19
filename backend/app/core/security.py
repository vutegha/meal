from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import get_settings

TokenType = Literal["access", "refresh"]
ALGORITHM = "HS256"

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


@dataclass(frozen=True)
class Claims:
    user_id: UUID
    session_id: UUID
    generation: int


def create_token(
    user_id: UUID, token_type: TokenType, session_id: UUID, generation: int = 0
) -> str:
    settings = get_settings()
    lifetime = (
        timedelta(minutes=settings.access_token_minutes)
        if token_type == "access"
        else timedelta(days=settings.refresh_token_days)
    )
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": token_type,
        "sid": str(session_id),
        "iat": now,
        "exp": now + lifetime,
    }
    if token_type == "refresh":
        payload["gen"] = generation
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str, expected_type: TokenType) -> Claims | None:
    """Contenu du jeton, ou None s'il est invalide, expiré ou d'un autre type."""
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])
        if payload.get("type") != expected_type:
            return None
        return Claims(
            user_id=UUID(payload["sub"]),
            session_id=UUID(payload["sid"]),
            generation=int(payload.get("gen", 0)),
        )
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        return None
