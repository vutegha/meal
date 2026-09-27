from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models import ReportStatus
from app.schemas.tor import DraftSection, TorSection


class DraftIndicatorSuggestion(BaseModel):
    indicator_code: str
    value: float
    justification: str = Field(description="Ce que dit la source, en une phrase")
    source_ref: str = Field(description="Identifiant de la source, ex. S3")


class ReportDraft(BaseModel):
    title: str = Field(description="Titre, ex. « Rapport : formation AVEC de Kiwanja »")
    sections: list[DraftSection]
    missing_information: list[str]
    indicator_suggestions: list[DraftIndicatorSuggestion]


class ReportSource(BaseModel):
    ref: str
    label: str
    evidence_id: UUID | None = None


class IndicatorSuggestion(BaseModel):
    indicator_id: UUID
    code: str
    name: str
    unit: str
    value: Decimal
    justification: str
    source_ref: str
    applied_value_id: UUID | None = None


class ReportSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    execution_id: UUID
    title: str
    status: ReportStatus
    version: int
    updated_at: datetime


class ReportOut(ReportSummary):
    project_id: UUID
    sections: list[TorSection]
    sources: list[ReportSource]
    missing_information: list[str]
    indicator_suggestions: list[IndicatorSuggestion]
    review_comment: str
    submitted_at: datetime | None
    approved_at: datetime | None
    created_at: datetime


class ApplySuggestionIn(BaseModel):
    value: Decimal | None = Field(default=None, description="Valeur corrigée, sinon celle proposée")
