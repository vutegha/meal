"""Reconnaissance de caractères des pages scannées, par la lecture d'images du modèle.

Aucune dépendance système : la page est rendue en image (PyMuPDF ou Pillow) puis lue par le
modèle, qui renvoie le texte transcrit. Le texte rejoint l'index plein texte comme les autres.
"""

import asyncio
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.documents.extract import ExtractionError, page_image
from app.documents.storage import get_storage
from app.llm.client import LLMError
from app.llm.prompts import ocr as prompt
from app.models import DocumentPage, DocumentStatus, Job, SourceDocument
from app.services.ai import call_structured


class OcrPage(BaseModel):
    text: str
    legible: bool


async def run_document_ocr(session: AsyncSession, job: Job) -> dict[str, Any]:
    document_id = UUID(job.params["document_id"])
    try:
        return await _read_pages(session, job, document_id)
    except (LLMError, ExtractionError) as exc:
        # Le document ne doit pas rester « en cours » : on enregistre l'échec à part.
        await session.rollback()
        document = await session.get_one(SourceDocument, document_id)
        document.status = DocumentStatus.FAILED
        document.error = f"Reconnaissance du texte impossible : {exc}"
        await session.commit()
        raise LLMError(document.error) from exc


async def _read_pages(session: AsyncSession, job: Job, document_id: UUID) -> dict[str, Any]:
    document = await session.get_one(SourceDocument, document_id)
    data = await get_storage().get(document.storage_key)
    pages = {
        p.number: p
        for p in await session.scalars(
            select(DocumentPage).where(DocumentPage.document_id == document.id)
        )
    }
    illegible = []
    for number in job.params["pages"]:
        image = await asyncio.to_thread(page_image, data, document.kind, number)
        result = await call_structured(
            session,
            organization_id=document.organization_id,
            project_id=document.project_id,
            purpose="document_ocr",
            prompt_version=prompt.VERSION,
            model=get_settings().llm_model_ocr,
            system=prompt.SYSTEM,
            content=prompt.build_content(image, number, document.filename),
            output_type=OcrPage,
            effort="low",
        )
        page = pages[number]
        page.text = result.output.text.replace("\x00", "").strip()
        if not result.output.legible or not page.text:
            illegible.append(number)
    await session.flush()
    chars = sum(len(p.text) for p in pages.values())
    if not chars:
        document.status = DocumentStatus.FAILED
        document.error = "Aucun texte lisible sur les pages scannées."
    else:
        document.status = DocumentStatus.EXTRACTED
        document.text_chars = chars
        if illegible:
            listed = ", ".join(str(n) for n in illegible)
            document.error = f"Pages peu lisibles, à vérifier : {listed}."
    return {"document_id": str(document.id), "pages": len(job.params["pages"])}
