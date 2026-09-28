"""Tâches longues : création, exécution (dans la requête ou par le worker ARQ) et suivi."""

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import bind_org, system_session
from app.llm.client import LLMError
from app.models import Job, JobStatus
from app.services.extraction import run_logframe_extraction
from app.services.ocr import run_document_ocr
from app.services.periodic import run_periodic_generation
from app.services.report import run_report_generation
from app.services.tor import run_tor_generation

logger = logging.getLogger(__name__)

Handler = Callable[[AsyncSession, Job], Awaitable[dict[str, Any]]]

HANDLERS: dict[str, Handler] = {
    "logframe_extraction": run_logframe_extraction,
    "tor_generation": run_tor_generation,
    "report_generation": run_report_generation,
    "periodic_generation": run_periodic_generation,
    "document_ocr": run_document_ocr,
}


async def run_job(job_id: UUID) -> None:
    async with system_session() as session:
        job = await session.get_one(Job, job_id)
        await bind_org(session, job.organization_id)
        job.status = JobStatus.RUNNING
        await session.commit()
        try:
            job.result = await HANDLERS[job.kind](session, job)
            job.status = JobStatus.SUCCEEDED
        except Exception as exc:
            if not isinstance(exc, LLMError):
                logger.exception("Échec de la tâche %s", job_id)
            await session.rollback()
            job = await session.get_one(Job, job_id)
            job.status = JobStatus.FAILED
            job.error = str(exc) if isinstance(exc, LLMError) else "Erreur inattendue du serveur."
        job.finished_at = datetime.now(UTC)
        await session.commit()


async def enqueue(job: Job) -> None:
    if get_settings().jobs_inline:
        await run_job(job.id)
        return
    from arq import create_pool
    from arq.connections import RedisSettings

    pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    try:
        await pool.enqueue_job("run_job_task", str(job.id))
    finally:
        await pool.aclose()
