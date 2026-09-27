"""Extraction du cadre logique par l'IA et vérification des citations."""

import re
import unicodedata
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.llm.client import LLMError
from app.llm.prompts import logframe_extraction as prompt
from app.models import AiProposal, DocumentStatus, Job, Project, SourceDocument
from app.schemas.ai import (
    LogframeExtraction,
    LogframeProposal,
    ProposedBudgetLine,
    ProposedIndicator,
    ProposedNode,
)
from app.services.ai import call_structured

_QUOTES = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "«": '"', "»": '"', "–": "-"})


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_QUOTES).lower()
    return re.sub(r"\s+", " ", text).strip()


class QuoteChecker:
    """Vérifie qu'un extrait cité figure bien dans le document (et corrige la page si besoin)."""

    def __init__(self, documents: list[SourceDocument]) -> None:
        self.pages = {
            (index, page.number): normalize(page.text)
            for index, document in enumerate(documents, start=1)
            for page in document.pages
        }

    def check(self, item: Any) -> bool:
        quote = normalize(item.source_quote or "")
        if len(quote) < 8:
            return False
        expected = (item.source_document, item.source_page)
        if expected in self.pages and quote in self.pages[expected]:
            return True
        for (document, page), text in self.pages.items():
            if quote in text:
                item.source_document, item.source_page = document, page
                return True
        return False


def verify(extraction: LogframeExtraction, documents: list[SourceDocument]) -> LogframeProposal:
    checker = QuoteChecker(documents)

    def mark(item: Any, cls: Any) -> Any:
        proposed = cls.model_validate(item.model_dump())
        proposed.verified = checker.check(proposed)
        return proposed

    return LogframeProposal(
        summary=extraction.summary,
        currency=extraction.currency,
        documents=[d.filename for d in documents],
        nodes=[mark(n, ProposedNode) for n in extraction.nodes],
        indicators=[mark(i, ProposedIndicator) for i in extraction.indicators],
        budget_lines=[mark(b, ProposedBudgetLine) for b in extraction.budget_lines],
        missing_information=extraction.missing_information,
    )


async def run_logframe_extraction(session: AsyncSession, job: Job) -> dict[str, Any]:
    project = await session.get_one(Project, job.project_id)
    documents = list(
        await session.scalars(
            select(SourceDocument)
            .where(
                SourceDocument.project_id == project.id,
                SourceDocument.status == DocumentStatus.EXTRACTED,
            )
            .options(selectinload(SourceDocument.pages))
            .order_by(SourceDocument.created_at)
        )
    )
    if not documents:
        raise LLMError("Aucun document lisible n'a été importé pour ce projet.")

    settings = get_settings()
    total_chars = sum(d.text_chars for d in documents)
    if total_chars > settings.llm_max_document_chars:
        raise LLMError(
            f"Les documents sont trop volumineux pour une seule extraction ({total_chars} "
            f"caractères, maximum {settings.llm_max_document_chars}). Retirez les annexes "
            "non utiles puis relancez."
        )

    content = prompt.build_content(
        [(d.filename, [(p.number, p.text) for p in d.pages]) for d in documents]
    )
    result = await call_structured(
        session,
        organization_id=project.organization_id,
        project_id=project.id,
        purpose="logframe_extraction",
        prompt_version=prompt.VERSION,
        model=settings.llm_model_extraction,
        system=prompt.SYSTEM,
        content=content,
        output_type=LogframeExtraction,
    )
    proposal_payload = verify(result.output, documents)
    proposal = AiProposal(
        organization_id=project.organization_id,
        project_id=project.id,
        job_id=job.id,
        kind="logframe",
        payload=proposal_payload.model_dump(mode="json"),
    )
    session.add(proposal)
    await session.flush()
    return {
        "proposal_id": str(proposal.id),
        "nodes": len(proposal_payload.nodes),
        "indicators": len(proposal_payload.indicators),
        "budget_lines": len(proposal_payload.budget_lines),
    }
