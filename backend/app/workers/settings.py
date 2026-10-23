"""Configuration du worker ARQ. Lancer avec : arq app.workers.settings.WorkerSettings"""

from typing import Any
from uuid import UUID

from arq import cron
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.db import system_session
from app.services.jobs import run_job
from app.services.retention import purge


async def run_job_task(ctx: dict[str, Any], job_id: str) -> None:
    await run_job(UUID(job_id))


async def purge_task(ctx: dict[str, Any]) -> None:
    async with system_session() as session:
        await purge(session)
        await session.commit()


class WorkerSettings:
    functions = [run_job_task]
    # Durées de conservation des données personnelles, chaque nuit.
    cron_jobs = [cron(purge_task, hour=3, minute=0, run_at_startup=False)]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    # Les extractions sur de longs documents peuvent durer plusieurs minutes.
    job_timeout = 1800
