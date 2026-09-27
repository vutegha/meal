"""Configuration du worker ARQ. Lancer avec : arq app.workers.settings.WorkerSettings"""

from typing import Any

from arq.connections import RedisSettings

from app.core.config import get_settings


async def ping(ctx: dict[str, Any]) -> str:
    """Tâche de vérification ; les tâches IA et documents arrivent aux étapes 3 et 4."""
    return "pong"


class WorkerSettings:
    functions = [ping]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
