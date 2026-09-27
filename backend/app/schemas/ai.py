from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models import DocumentStatus, JobStatus, ProposalStatus

Level = Literal["goal", "outcome", "output", "activity", "sub_activity"]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Sortie structurée demandée au modèle --------------------------------------
# Tous les champs sont obligatoires (éventuellement nuls) : c'est ce que les sorties
# structurées garantissent le mieux.


class ExtractedNode(BaseModel):
    ref: str = Field(description="Identifiant unique dans cette réponse, ex. OS1, R1.2, A1.2.3")
    parent_ref: str | None = Field(description="ref du parent ; null pour l'objectif général")
    level: Level
    code: str = Field(description="Code tel qu'écrit dans le document, sinon le ref")
    title: str
    assumptions: str = Field(description="Hypothèses ou risques associés, sinon chaîne vide")
    source_document: int | None = Field(description="Numéro du document source (1, 2…)")
    source_page: int | None
    source_quote: str = Field(description="Extrait exact du document, 5 à 30 mots")


class ExtractedIndicator(BaseModel):
    node_ref: str
    code: str
    name: str
    unit: str
    baseline: float | None
    target: float | None
    aggregation: Literal["sum", "latest"]
    disaggregations: list[str]
    source_of_verification: str
    source_document: int | None
    source_page: int | None
    source_quote: str


class ExtractedBudgetLine(BaseModel):
    activity_ref: str | None = Field(
        description="ref de l'activité ; null pour les coûts de support"
    )
    donor_line_code: str
    label: str
    category: str
    quantity: float
    unit: str
    unit_cost: float
    frequency: float
    is_estimate: bool = Field(description="true si le montant n'est pas écrit dans le document")
    source_document: int | None
    source_page: int | None
    source_quote: str


class LogframeExtraction(BaseModel):
    summary: str = Field(description="Résumé du projet en 3 à 5 phrases")
    currency: str | None = Field(description="Code ISO de la devise du budget, ex. USD")
    nodes: list[ExtractedNode]
    indicators: list[ExtractedIndicator]
    budget_lines: list[ExtractedBudgetLine]
    missing_information: list[str] = Field(
        description="Informations attendues dans un cadre logique mais absentes du document"
    )


# --- Proposition stockée (sortie du modèle + vérification des citations) -----------


class Verified(BaseModel):
    verified: bool = False


class ProposedNode(ExtractedNode, Verified):
    pass


class ProposedIndicator(ExtractedIndicator, Verified):
    pass


class ProposedBudgetLine(ExtractedBudgetLine, Verified):
    pass


class LogframeProposal(BaseModel):
    summary: str
    currency: str | None
    documents: list[str] = []
    nodes: list[ProposedNode]
    indicators: list[ProposedIndicator]
    budget_lines: list[ProposedBudgetLine]
    missing_information: list[str]


class ApplyLogframeIn(BaseModel):
    """Sous-ensemble (éventuellement corrigé) de la proposition retenu par l'utilisateur."""

    nodes: list[ExtractedNode]
    indicators: list[ExtractedIndicator] = []
    budget_lines: list[ExtractedBudgetLine] = []


# --- API ----------------------------------------------------------------------


class DocumentOut(ORMModel):
    id: UUID
    filename: str
    kind: str
    size_bytes: int
    status: DocumentStatus
    page_count: int
    text_chars: int
    error: str
    created_at: datetime


class SearchHit(BaseModel):
    document_id: UUID
    filename: str
    page: int
    snippet: str
    rank: float


class JobOut(ORMModel):
    id: UUID
    kind: str
    status: JobStatus
    result: dict[str, Any]
    error: str
    created_at: datetime
    finished_at: datetime | None


class ProposalOut(ORMModel):
    id: UUID
    kind: str
    status: ProposalStatus
    payload: dict[str, Any]
    created_at: datetime
    reviewed_at: datetime | None


class AiUsage(BaseModel):
    month_cost_usd: Decimal
    monthly_budget_usd: Decimal | None
    calls_this_month: int
