"""Tâches longues : création, exécution (dans la requête ou par le worker ARQ) et suivi.

Une tâche ne s'exécute qu'une fois : le worker la prend en charge en la faisant passer de « en
attente » à « en cours » ; une seconde livraison (redémarrage du worker, relance d'ARQ) la
trouve déjà prise et ne refait pas l'appel au modèle, qui serait facturé deux fois. Une tâche
interrompue, ou restée trop longtemps en attente, passe en échec avec un message clair.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import bind_org, system_session
from app.llm.client import LLMError
from app.models import Job, JobStatus
from app.services import ocr
from app.services.extraction import run_logframe_extraction
from app.services.periodic import run_periodic_generation
from app.services.report import run_report_generation
from app.services.tor import run_tor_generation

logger = logging.getLogger(__name__)

Handler = Callable[[AsyncSession, Job], Awaitable[dict[str, Any]]]
Abandon = Callable[[AsyncSession, Job, str], Awaitable[None]]

HANDLERS: dict[str, Handler] = {
    "logframe_extraction": run_logframe_extraction,
    "tor_generation": run_tor_generation,
    "report_generation": run_report_generation,
    "periodic_generation": run_periodic_generation,
    "document_ocr": ocr.run_document_ocr,
}
# Ce qu'il faut remettre d'aplomb quand une tâche est abandonnée sans avoir pu finir.
ON_ABANDON: dict[str, Abandon] = {"document_ocr": ocr.abandon}

# Durée maximale d'une tâche (les extractions sur de longs documents durent plusieurs minutes).
JOB_TIMEOUT = timedelta(minutes=30)
# Au-delà, une tâche « en cours » a été perdue (worker arrêté net) ; une tâche « en attente »
# ne sera plus attendue par personne.
RUNNING_TOO_LONG = JOB_TIMEOUT + timedelta(minutes=5)
QUEUED_TOO_LONG = timedelta(hours=2)

INTERRUPTED = "Tâche interrompue (délai dépassé ou arrêt du serveur). Relancez-la."
NOT_STARTED = "Tâche jamais démarrée (service des tâches arrêté). Relancez-la."
QUEUE_DOWN = "Service des tâches indisponible : réessayez dans quelques minutes."


class QueueUnavailable(Exception):
    """La tâche n'a pas pu être confiée au worker (Redis injoignable) ; elle est en échec."""


async def run_job(job_id: UUID) -> None:
    async with system_session() as session:
        claimed = await session.scalar(
            update(Job)
            .where(Job.id == job_id, Job.status == JobStatus.QUEUED)
            .values(status=JobStatus.RUNNING, started_at=datetime.now(UTC))
            .returning(Job.organization_id)
        )
        await session.commit()
        if claimed is None:
            logger.warning("Tâche %s déjà prise en charge ou terminée : pas relancée", job_id)
            return
        await bind_org(session, claimed)
        job = await session.get_one(Job, job_id)
        try:
            job.result = await HANDLERS[job.kind](session, job)
            job.status = JobStatus.SUCCEEDED
        except asyncio.CancelledError:
            # Délai d'ARQ dépassé ou arrêt du worker : la tâche ne reste pas « en cours ».
            await asyncio.shield(abandon(job_id, INTERRUPTED))
            raise
        except Exception as exc:
            if not isinstance(exc, LLMError):
                logger.exception("Échec de la tâche %s", job_id)
            await session.rollback()
            job = await session.get_one(Job, job_id)
            job.status = JobStatus.FAILED
            job.error = str(exc) if isinstance(exc, LLMError) else "Erreur inattendue du serveur."
        job.finished_at = datetime.now(UTC)
        await session.commit()


async def abandon(job_id: UUID, message: str) -> bool:
    """Passe en échec une tâche en attente ou en cours. Renvoie False si elle était finie."""
    async with system_session() as session:
        job = await session.get(Job, job_id, with_for_update=True)
        if job is None or job.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
            return False
        job.status = JobStatus.FAILED
        job.error = message
        job.finished_at = datetime.now(UTC)
        if hook := ON_ABANDON.get(job.kind):
            await hook(session, job, message)
        await session.commit()
    logger.warning("Tâche %s abandonnée : %s", job_id, message)
    return True


async def fail_stale() -> int:
    """Tâches perdues (worker arrêté net, file vidée) : passées en échec. Lancé par le worker."""
    now = datetime.now(UTC)
    async with system_session() as session:
        lost = (
            await session.execute(
                select(Job.id, Job.status).where(
                    or_(
                        and_(
                            Job.status == JobStatus.RUNNING,
                            Job.started_at < now - RUNNING_TOO_LONG,
                        ),
                        and_(
                            Job.status == JobStatus.QUEUED,
                            Job.created_at < now - QUEUED_TOO_LONG,
                        ),
                    )
                )
            )
        ).all()
    count = 0
    for job_id, job_status in lost:
        message = INTERRUPTED if job_status == JobStatus.RUNNING else NOT_STARTED
        count += await abandon(job_id, message)
    return count


async def enqueue(job: Job) -> None:
    if get_settings().jobs_inline:
        await run_job(job.id)
        return
    from arq import create_pool
    from arq.connections import RedisSettings

    try:
        redis = RedisSettings.from_dsn(get_settings().redis_url)
        # Une seule tentative : la personne attend la réponse.
        redis.conn_retries = 1
        pool = await create_pool(redis)
        try:
            # Identifiant ARQ = celui de la tâche : un double envoi n'en crée pas deux.
            await pool.enqueue_job("run_job_task", str(job.id), _job_id=str(job.id))
        finally:
            await pool.aclose()
    except Exception as exc:  # noqa: BLE001 - Redis injoignable, quelle que soit l'erreur
        logger.exception("Tâche %s non confiée au worker", job.id)
        await abandon(job.id, QUEUE_DOWN)
        raise QueueUnavailable(QUEUE_DOWN) from exc
