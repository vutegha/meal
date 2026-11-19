"""Configuration du worker ARQ. Lancer avec : arq app.workers.settings.WorkerSettings"""

from typing import Any
from uuid import UUID

from arq import cron
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.db import check_role, system_session
from app.services.jobs import JOB_TIMEOUT, fail_stale, run_job
from app.services.retention import purge


async def run_job_task(ctx: dict[str, Any], job_id: str) -> None:
    await run_job(UUID(job_id))


async def purge_task(ctx: dict[str, Any]) -> None:
    async with system_session() as session:
        await purge(session)
        await session.commit()


async def fail_stale_task(ctx: dict[str, Any]) -> None:
    await fail_stale()


async def startup(ctx: dict[str, Any]) -> None:
    await check_role()


class WorkerSettings:
    on_startup = startup
    functions = [run_job_task]
    cron_jobs = [
        # Durées de conservation des données personnelles, chaque nuit.
        cron(purge_task, hour=3, minute=0, run_at_startup=False),
        # Tâches perdues (worker arrêté net) passées en échec, au démarrage puis toutes les
        # 10 minutes.
        cron(fail_stale_task, minute=set(range(0, 60, 10)), run_at_startup=True),
    ]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    job_timeout = int(JOB_TIMEOUT.total_seconds())
