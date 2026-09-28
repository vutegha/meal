"""Recherche dans les documents du projet : plein texte, complété par le sens si possible.

Les deux classements (mots en commun et proximité de sens des embeddings) sont fusionnés par
rang réciproque (RRF). Sans service d'embeddings, ou s'il ne répond pas, la recherche reste en
plein texte : elle ne tombe jamais en panne à cause de la partie sémantique.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Text, cast, func, literal_column, select
from sqlalchemy.dialects.postgresql import TSQUERY
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.llm.embeddings import EmbeddingError, Embeddings, Kind, get_embedder
from app.models import AiCall, DocumentPage, Project, SourceDocument
from app.services.ai import log_call, month_cost

logger = logging.getLogger(__name__)

RRF_K = 60
CANDIDATES = 50
# Distance cosinus au-delà de laquelle une page n'est pas jugée proche par le sens.
MAX_DISTANCE = 0.65
BATCH = 64


@dataclass
class Hit:
    page_id: UUID
    score: float
    by_text: bool
    by_meaning: bool


def text_query(q: str, any_term: bool = False) -> Any:
    """Requête plein texte en français : tous les termes, ou n'importe lequel."""
    if not any_term:
        return func.websearch_to_tsquery(literal_column("'french'"), q)
    # plainto_tsquery exige tous les termes (&) ; on accepte n'importe lequel (|).
    words = cast(func.plainto_tsquery(literal_column("'french'"), q), Text)
    return cast(func.replace(words, "&", "|"), TSQUERY)


async def _embed(
    session: AsyncSession, project: Project, texts: list[str], kind: Kind
) -> Embeddings | None:
    embedder = get_embedder()
    if embedder is None:
        return None
    cap = Decimal(str(get_settings().ai_monthly_budget_usd))
    if cap > 0 and await month_cost(session, project.organization_id) >= cap:
        return None
    call = AiCall(
        organization_id=project.organization_id,
        project_id=project.id,
        purpose="document_embeddings" if kind == "document" else "search_embeddings",
        prompt_version="v1",
        model=get_settings().embeddings_model,
    )
    vectors: list[list[float]] = []
    tokens = 0
    try:
        for start in range(0, len(texts), BATCH):
            result = await embedder.embed(texts[start : start + BATCH], kind)
            vectors += result.vectors
            tokens += result.tokens
            call.model = result.model
    except EmbeddingError as exc:
        logger.warning("Embeddings indisponibles : %s", exc)
        call.status, call.error = "error", str(exc)
        await log_call(call)
        return None
    embeddings = Embeddings(vectors=vectors, tokens=tokens, model=call.model)
    call.status, call.input_tokens, call.cost_usd = "ok", tokens, embeddings.cost_usd
    await log_call(call)
    return embeddings


async def ensure_embeddings(session: AsyncSession, project: Project) -> None:
    """Calcule les embeddings des pages qui n'en ont pas encore (par lots, à la demande)."""
    if get_embedder() is None:
        return
    pages = (
        await session.scalars(
            select(DocumentPage)
            .join(SourceDocument)
            .where(
                SourceDocument.project_id == project.id,
                DocumentPage.embedding.is_(None),
                func.length(func.trim(DocumentPage.text)) > 0,
            )
            .order_by(DocumentPage.document_id, DocumentPage.number)
            .limit(get_settings().embeddings_batch_pages)
        )
    ).all()
    if not pages:
        return
    embeddings = await _embed(session, project, [p.text for p in pages], "document")
    if embeddings is None:
        return
    for page, vector in zip(pages, embeddings.vectors, strict=True):
        page.embedding = vector
    await session.flush()


async def search_pages(
    session: AsyncSession, project: Project, q: str, limit: int, any_term: bool = False
) -> list[Hit]:
    query = text_query(q, any_term)
    in_project = SourceDocument.project_id == project.id
    by_text = list(
        await session.scalars(
            select(DocumentPage.id)
            .join(SourceDocument)
            .where(in_project, DocumentPage.search.op("@@")(query))
            .order_by(func.ts_rank(DocumentPage.search, query).desc())
            .limit(CANDIDATES)
        )
    )
    by_meaning: list[UUID] = []
    if get_embedder() is not None:
        await ensure_embeddings(session, project)
        embedded = await _embed(session, project, [q], "query")
        if embedded:
            distance = DocumentPage.embedding.cosine_distance(embedded.vectors[0])
            by_meaning = list(
                await session.scalars(
                    select(DocumentPage.id)
                    .join(SourceDocument)
                    .where(
                        in_project,
                        DocumentPage.embedding.is_not(None),
                        distance < MAX_DISTANCE,
                    )
                    .order_by(distance)
                    .limit(CANDIDATES)
                )
            )
    return fuse(by_text, by_meaning)[:limit]


def fuse(by_text: list[UUID], by_meaning: list[UUID]) -> list[Hit]:
    """Fusion par rang réciproque : une page bien classée des deux côtés passe devant."""
    hits: dict[UUID, Hit] = {}
    for ranking, attr in ((by_text, "by_text"), (by_meaning, "by_meaning")):
        for rank, page_id in enumerate(ranking, start=1):
            hit = hits.setdefault(page_id, Hit(page_id, 0.0, False, False))
            hit.score += 1 / (RRF_K + rank)
            setattr(hit, attr, True)
    return sorted(hits.values(), key=lambda h: h.score, reverse=True)
