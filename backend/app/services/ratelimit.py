"""Limitation des tentatives de connexion.

Compteur d'échecs par fenêtre fixe, partagé entre les processus de l'API par Redis. Les tests
et le développement sans Redis utilisent un compteur en mémoire (LOGIN_RATE_LIMIT_STORAGE).
"""

import contextlib
import logging
import time

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings

logger = logging.getLogger(__name__)

PREFIX = "wemeal:login-fail:"

_memory: dict[str, tuple[int, float]] = {}
_redis: Redis | None = None


def _client() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(get_settings().redis_url)
    return _redis


async def ping() -> None:
    await _client().ping()


def _use_memory() -> bool:
    return get_settings().login_rate_limit_storage == "memory"


async def failures(key: str) -> int:
    if not _use_memory():
        try:
            value = await _client().get(PREFIX + key)
            return int(value or 0)
        except RedisError:
            logger.warning("Redis indisponible : limitation des connexions en mémoire")
    count, until = _memory.get(key, (0, 0.0))
    return count if until > time.monotonic() else 0


async def add_failure(key: str) -> None:
    window = get_settings().login_window_minutes * 60
    if not _use_memory():
        try:
            async with _client().pipeline(transaction=True) as pipe:
                pipe.incr(PREFIX + key)
                pipe.expire(PREFIX + key, window, nx=True)
                await pipe.execute()
            return
        except RedisError:
            logger.warning("Redis indisponible : limitation des connexions en mémoire")
    count = await failures(key)
    _, until = _memory.get(key, (0, 0.0))
    if count == 0:
        until = time.monotonic() + window
    _memory[key] = (count + 1, until)


async def reset(key: str) -> None:
    _memory.pop(key, None)
    if not _use_memory():
        with contextlib.suppress(RedisError):
            await _client().delete(PREFIX + key)


def clear_memory() -> None:
    _memory.clear()
