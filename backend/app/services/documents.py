import asyncio
import hashlib
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.documents.extract import ExtractionError, detect_kind, extract_pages
from app.documents.storage import get_storage
from app.models import DocumentPage, DocumentStatus, Job, Project, SourceDocument


async def ingest(
    session: AsyncSession,
    *,
    project: Project,
    filename: str,
    content_type: str | None,
    data: bytes,
    uploaded_by: UUID,
) -> SourceDocument:
    """Stocke le fichier, en extrait le texte page par page et l'indexe."""
    settings = get_settings()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"Fichier trop volumineux (maximum {settings.max_upload_mb} Mo)",
        )
    kind = detect_kind(filename, content_type)
    if kind is None:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Format non pris en charge : PDF, Word (.docx), Excel (.xlsx), texte ou image "
            "(JPEG, PNG)",
        )
    digest = hashlib.sha256(data).hexdigest()
    if await session.scalar(
        select(SourceDocument.id).where(
            SourceDocument.project_id == project.id, SourceDocument.sha256 == digest
        )
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ce document a déjà été importé")

    key = f"{project.organization_id}/{project.id}/{uuid4()}-{filename[-120:]}"
    await get_storage().put(key, data, content_type or "application/octet-stream")
    document = SourceDocument(
        organization_id=project.organization_id,
        project_id=project.id,
        filename=filename[:300],
        kind=kind,
        mime_type=content_type or "application/octet-stream",
        size_bytes=len(data),
        sha256=digest,
        storage_key=key,
        uploaded_by=uploaded_by,
    )
    session.add(document)
    await session.flush()

    try:
        pages = await asyncio.to_thread(extract_pages, data, kind)
    except ExtractionError as exc:
        document.status = DocumentStatus.FAILED
        document.error = str(exc)
        return document

    for page in pages:
        session.add(
            DocumentPage(
                organization_id=project.organization_id,
                document_id=document.id,
                number=page.number,
                # PostgreSQL refuse le caractère nul dans le texte.
                text=page.text.replace("\x00", ""),
            )
        )
    document.page_count = len(pages)
    document.text_chars = sum(len(p.text) for p in pages)
    scanned = [p.number for p in pages if p.needs_ocr]
    if not scanned:
        document.status = DocumentStatus.EXTRACTED
        return document
    # Pages scannées : la reconnaissance de caractères part en tâche de fond.
    document.status = DocumentStatus.OCR
    limit = settings.ocr_max_pages
    if len(scanned) > limit:
        document.error = f"Seules les {limit} premières pages scannées sont lues."
    await session.flush()
    session.add(
        Job(
            organization_id=project.organization_id,
            project_id=project.id,
            kind="document_ocr",
            params={"document_id": str(document.id), "pages": scanned[:limit]},
            created_by=uploaded_by,
        )
    )
    return document


async def pending_ocr(session: AsyncSession, document: SourceDocument) -> Job | None:
    """Tâche de reconnaissance créée à l'import, à lancer une fois l'import enregistré."""
    if document.status != DocumentStatus.OCR:
        return None
    jobs = await session.scalars(
        select(Job).where(Job.kind == "document_ocr", Job.project_id == document.project_id)
    )
    return next((j for j in jobs if j.params.get("document_id") == str(document.id)), None)
