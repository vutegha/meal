from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import EvidenceKind, ExecutionStatus


class Participants(BaseModel):
    women: int = Field(default=0, ge=0)
    men: int = Field(default=0, ge=0)
    girls: int = Field(default=0, ge=0)
    boys: int = Field(default=0, ge=0)
    # Sous-ensemble des participants ci-dessus, pas une catégorie de plus.
    with_disability: int = Field(default=0, ge=0)

    @property
    def total(self) -> int:
        return self.women + self.men + self.girls + self.boys

    @model_validator(mode="after")
    def disability_within_total(self) -> "Participants":
        if self.with_disability > self.total:
            raise ValueError("Les personnes handicapées sont comptées parmi les participants")
        return self


class ExecutionIn(BaseModel):
    activity_id: UUID
    title: str = Field(default="", max_length=300)
    start_date: date
    end_date: date | None = None
    location: str = Field(default="", max_length=300)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    participants: Participants = Participants()
    notes: str = Field(default="", max_length=20_000)
    status: ExecutionStatus = ExecutionStatus.IN_PROGRESS
    client_uuid: UUID | None = None

    @model_validator(mode="after")
    def dates_in_order(self) -> "ExecutionIn":
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("La date de fin précède la date de début")
        return self


class ExecutionUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    start_date: date | None = None
    end_date: date | None = None
    location: str | None = Field(default=None, max_length=300)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    participants: Participants | None = None
    notes: str | None = Field(default=None, max_length=20_000)
    status: ExecutionStatus | None = None


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    execution_id: UUID
    kind: EvidenceKind
    filename: str
    content_type: str
    size_bytes: int
    caption: str
    taken_at: datetime | None
    latitude: Decimal | None
    longitude: Decimal | None
    consent_given: bool
    has_thumbnail: bool
    page_count: int
    # Visages détectés sur la photo ; floutés sur la vignette sauf décision contraire.
    faces: int = 0
    blur_faces: bool = True
    created_at: datetime


class EvidenceUpdate(BaseModel):
    kind: EvidenceKind | None = None
    caption: str | None = Field(default=None, max_length=2000)
    consent_given: bool | None = None
    blur_faces: bool | None = None


class ExecutionExpenseIn(BaseModel):
    budget_line_id: UUID
    amount: Decimal = Field(gt=0)
    spent_on: date
    reference: str = Field(default="", max_length=100)
    description: str = Field(default="", max_length=2000)


class ExecutionExpenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    budget_line_id: UUID
    amount: Decimal
    spent_on: date
    reference: str
    description: str


class ExecutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    activity_id: UUID
    title: str
    start_date: date
    end_date: date | None
    location: str
    latitude: Decimal | None
    longitude: Decimal | None
    participants: Participants
    participants_total: int
    notes: str
    status: ExecutionStatus
    client_uuid: UUID | None
    evidence_count: int
    spent: Decimal
    created_at: datetime


class ExecutionDetail(ExecutionOut):
    evidence: list[EvidenceOut]
    expenses: list[ExecutionExpenseOut]
    planned: Decimal
