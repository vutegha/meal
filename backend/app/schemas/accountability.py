from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import FeedbackCategory, FeedbackChannel, FeedbackStatus, PeriodicKind
from app.schemas.report import ReportSource
from app.schemas.tor import DraftSection, TorSection

# --- Plaintes et retours ----------------------------------------------------------------


class FeedbackIn(BaseModel):
    received_on: date = Field(default_factory=date.today)
    channel: FeedbackChannel
    category: FeedbackCategory
    # Laissé vide, il est déduit de la catégorie (fraude, exploitation, sécurité).
    sensitive: bool | None = None
    description: str = Field(min_length=3, max_length=10_000)
    location: str = Field(default="", max_length=300)
    activity_id: UUID | None = None
    anonymous: bool = False
    contact: str = Field(default="", max_length=300)
    client_uuid: UUID | None = None


class FeedbackClassifyIn(BaseModel):
    description: str = Field(min_length=3, max_length=10_000)
    channel: FeedbackChannel | None = None


class FeedbackSuggestion(BaseModel):
    """Classement proposé par le modèle léger ; la personne qui saisit le valide."""

    category: FeedbackCategory
    sensitive: bool
    urgency: Literal["low", "normal", "high"]
    summary: str
    justification: str


class FeedbackUpdate(BaseModel):
    received_on: date | None = None
    channel: FeedbackChannel | None = None
    category: FeedbackCategory | None = None
    sensitive: bool | None = None
    description: str | None = Field(default=None, min_length=3, max_length=10_000)
    location: str | None = Field(default=None, max_length=300)
    activity_id: UUID | None = None
    anonymous: bool | None = None
    contact: str | None = Field(default=None, max_length=300)
    status: FeedbackStatus | None = None
    assigned_to: UUID | None = None
    response: str | None = Field(default=None, max_length=10_000)
    responded_on: date | None = None


class FeedbackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    reference: str
    received_on: date
    channel: FeedbackChannel
    category: FeedbackCategory
    sensitive: bool
    description: str
    location: str
    activity_id: UUID | None
    anonymous: bool
    contact: str
    status: FeedbackStatus
    assigned_to: UUID | None
    response: str
    responded_on: date | None
    closed_on: date | None
    created_by: UUID | None
    client_uuid: UUID | None
    created_at: datetime
    updated_at: datetime
    due_on: date
    overdue: bool
    response_days: int | None


class FeedbackStats(BaseModel):
    total: int
    open: int
    overdue: int
    response_rate: float | None
    average_response_days: float | None
    by_status: dict[str, int]
    by_category: dict[str, int]
    by_channel: dict[str, int]
    # Entrées sensibles comptées ici mais masquées pour l'utilisateur courant.
    hidden_sensitive: int


# --- Leçons apprises -----------------------------------------------------------------


def _clean_tags(tags: list[str]) -> list[str]:
    seen: list[str] = []
    for tag in tags:
        clean = " ".join(tag.strip().lower().split())[:40]
        if clean and clean not in seen:
            seen.append(clean)
    return seen[:10]


class LessonIn(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    description: str = Field(default="", max_length=10_000)
    recommendation: str = Field(default="", max_length=10_000)
    tags: list[str] = []
    activity_id: UUID | None = None
    source_report_id: UUID | None = None

    _tags = field_validator("tags")(_clean_tags)


class LessonUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=300)
    description: str | None = Field(default=None, max_length=10_000)
    recommendation: str | None = Field(default=None, max_length=10_000)
    tags: list[str] | None = None
    activity_id: UUID | None = None

    @field_validator("tags")
    @classmethod
    def _tags(cls, tags: list[str] | None) -> list[str] | None:
        return None if tags is None else _clean_tags(tags)


class LessonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    project_code: str = ""
    title: str
    description: str
    recommendation: str
    tags: list[str]
    activity_id: UUID | None
    source_report_id: UUID | None
    created_by: UUID | None
    created_at: datetime


# --- Rapports périodiques -------------------------------------------------------------


class PeriodicIn(BaseModel):
    kind: PeriodicKind
    period_start: date
    period_end: date
    instructions: str = Field(default="", max_length=4000)
    # Modèle à suivre ; sinon celui du bailleur du projet ou de l'organisation.
    template_id: UUID | None = None

    @model_validator(mode="after")
    def _period(self) -> "PeriodicIn":
        if self.period_end < self.period_start:
            raise ValueError("La fin de la période précède son début")
        return self


class PeriodicSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: PeriodicKind
    period_start: date
    period_end: date
    title: str
    status: str
    version: int
    updated_at: datetime


class PeriodicOut(PeriodicSummary):
    project_id: UUID
    template_id: UUID | None = None
    sections: list[TorSection]
    sources: list[ReportSource]
    missing_information: list[str]
    instructions: str
    review_comment: str
    submitted_at: datetime | None
    approved_at: datetime | None
    created_at: datetime


class PeriodicDraft(BaseModel):
    title: str = Field(description="Titre, ex. « Rapport trimestriel T1 2026 »")
    sections: list[DraftSection]
    missing_information: list[str]
