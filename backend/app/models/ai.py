import enum
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Computed,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, IdMixin, TimestampMixin
from app.llm.embeddings import DIMENSIONS


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class DocumentStatus(enum.StrEnum):
    UPLOADED = "uploaded"
    # Pages scannées en cours de reconnaissance de caractères (voir services/ocr.py).
    OCR = "ocr"
    EXTRACTED = "extracted"
    FAILED = "failed"


class JobStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ProposalStatus(enum.StrEnum):
    PENDING = "pending"
    APPLIED = "applied"
    REJECTED = "rejected"


class SourceDocument(IdMixin, TimestampMixin, Base):
    __tablename__ = "source_documents"
    __table_args__ = (UniqueConstraint("project_id", "sha256"),)

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(10))
    mime_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(300))
    status: Mapped[DocumentStatus] = mapped_column(
        _enum(DocumentStatus, "document_status"), default=DocumentStatus.UPLOADED
    )
    page_count: Mapped[int] = mapped_column(default=0)
    text_chars: Mapped[int] = mapped_column(default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    uploaded_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    pages: Mapped[list["DocumentPage"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentPage.number"
    )


class DocumentPage(IdMixin, Base):
    """Texte d'une page : unité de citation et de recherche plein texte."""

    __tablename__ = "document_pages"
    __table_args__ = (
        UniqueConstraint("document_id", "number"),
        Index("ix_document_pages_search", "search", postgresql_using="gin"),
        Index(
            "ix_document_pages_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    search: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('french', text)", persisted=True)
    )
    # Embedding de la page (recherche sémantique), calculé à la première recherche.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(DIMENSIONS), nullable=True)

    document: Mapped[SourceDocument] = relationship(back_populates="pages")


class Job(IdMixin, TimestampMixin, Base):
    __tablename__ = "jobs"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(60))
    status: Mapped[JobStatus] = mapped_column(
        _enum(JobStatus, "job_status"), default=JobStatus.QUEUED
    )
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AiCall(IdMixin, TimestampMixin, Base):
    """Journal de chaque appel au modèle : coût, durée, résultat."""

    __tablename__ = "ai_calls"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    purpose: Mapped[str] = mapped_column(String(60))
    prompt_version: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(80))
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    cache_read_tokens: Mapped[int] = mapped_column(default=0)
    cache_write_tokens: Mapped[int] = mapped_column(default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal(0))
    duration_ms: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(20))
    error: Mapped[str] = mapped_column(Text, default="")
    request_id: Mapped[str] = mapped_column(String(100), default="")


class AiProposal(IdMixin, TimestampMixin, Base):
    """Proposition de l'IA, soumise à validation humaine avant tout enregistrement."""

    __tablename__ = "ai_proposals"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[ProposalStatus] = mapped_column(
        _enum(ProposalStatus, "proposal_status"), default=ProposalStatus.PENDING
    )
    reviewed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
