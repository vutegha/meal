from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class FeedbackMatch(BaseModel):
    id: UUID
    project_code: str
    reference: str
    received_on: date
    category: str
    status: str
    sensitive: bool
    contact: str
    description: str
    response: str
    anonymized: bool
    messages: list[dict[str, Any]]


class SubmissionMatch(BaseModel):
    id: UUID
    project_code: str
    form_title: str
    collected_at: datetime
    location: str
    answers: dict[str, Any]


class EvidenceMatch(BaseModel):
    """Preuve qui cite la personne (légende ou texte) : à vérifier, jamais effacée d'office."""

    id: UUID
    project_code: str
    filename: str
    kind: str
    caption: str
    excerpt: str


class PersonalDataResult(BaseModel):
    query: str
    feedback: list[FeedbackMatch]
    submissions: list[SubmissionMatch]
    evidence: list[EvidenceMatch]


class ErasureIn(BaseModel):
    feedback_ids: list[UUID] = Field(default_factory=list, max_length=500)
    submission_ids: list[UUID] = Field(default_factory=list, max_length=500)
    # Motif inscrit au journal (demande de la personne, erreur de saisie…).
    reason: str = Field(min_length=3, max_length=300)


class ErasureOut(BaseModel):
    feedback: int
    submissions: int
