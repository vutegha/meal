"""Configuration du worker ARQ. Lancer avec : arq app.workers.settings.WorkerSettings"""

from typing import Any
from uuid import UUID

from arq.connections import RedisSettings

from app.core.config import get_settings
from app.services.jobs import run_job


async def run_job_task(ctx: dict[str, Any], job_id: str) -> None:
    await run_job(UUID(job_id))


class WorkerSettings:
    functions = [run_job_task]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    # Les extractions sur de longs documents peuvent durer plusieurs minutes.
    job_timeout = 1800
