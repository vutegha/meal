"""Appels au modèle avec plafond de dépense et journalisation systématique."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, TypeVar
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import SessionLocal, bind_org
from app.llm.client import Effort, LLMError, LLMResult, get_llm
from app.llm.pricing import estimate_cost
from app.models import AiCall

T = TypeVar("T", bound=BaseModel)


def month_start() -> datetime:
    now = datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def month_cost(session: AsyncSession, org_id: UUID) -> Decimal:
    total = await session.scalar(
        select(func.coalesce(func.sum(AiCall.cost_usd), 0)).where(
            AiCall.organization_id == org_id, AiCall.created_at >= month_start()
        )
    )
    return Decimal(total or 0)


async def call_structured(
    session: AsyncSession,
    *,
    organization_id: UUID,
    project_id: UUID | None,
    purpose: str,
    prompt_version: str,
    model: str,
    system: str,
    content: list[dict[str, Any]],
    output_type: type[T],
    effort: Effort | None = "high",
) -> LLMResult[T]:
    settings = get_settings()
    cap = Decimal(str(settings.ai_monthly_budget_usd))
    if cap > 0 and await month_cost(session, organization_id) >= cap:
        raise LLMError(
            f"Le plafond mensuel de dépenses IA de l'organisation ({cap} USD) est atteint."
        )

    call = AiCall(
        organization_id=organization_id,
        project_id=project_id,
        purpose=purpose,
        prompt_version=prompt_version,
        model=model,
    )
    try:
        result = await get_llm().structured(
            model=model, system=system, content=content, output_type=output_type, effort=effort
        )
    except LLMError as exc:
        call.status, call.error = "error", str(exc)
        await _log(call)
        raise
    call.status = "ok"
    call.model = result.model or model
    call.input_tokens = result.input_tokens
    call.output_tokens = result.output_tokens
    call.cache_read_tokens = result.cache_read_tokens
    call.cache_write_tokens = result.cache_write_tokens
    call.duration_ms = result.duration_ms
    call.request_id = result.request_id
    call.cost_usd = estimate_cost(
        model,
        result.input_tokens,
        result.output_tokens,
        result.cache_read_tokens,
        result.cache_write_tokens,
    )
    await _log(call)
    return result


async def _log(call: AiCall) -> None:
    """Enregistre l'appel dans sa propre transaction : il reste tracé même si la suite échoue."""
    async with SessionLocal() as log_session:
        await bind_org(log_session, call.organization_id)
        log_session.add(call)
        await log_session.commit()
