from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models import TorStatus


class TorSection(BaseModel):
    key: str = Field(max_length=60)
    title: str = Field(max_length=200)
    content: str = Field(default="", max_length=50_000)


# --- Sortie structurée demandée au modèle ------------------------------------------


class DraftSection(BaseModel):
    key: str = Field(description="Clé de la section, telle que donnée dans la demande")
    content: str = Field(description="Contenu de la section en Markdown simple")


class TorDraft(BaseModel):
    title: str = Field(description="Titre des TdR, ex. « TdR : formation des membres des AVEC »")
    sections: list[DraftSection]
    missing_information: list[str] = Field(
        description="Informations nécessaires aux TdR mais absentes des sources"
    )


# --- API ------------------------------------------------------------------------


class TorUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    sections: list[TorSection]


class TorReview(BaseModel):
    comment: str = Field(default="", max_length=5000)


class TorSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    activity_id: UUID
    title: str
    status: TorStatus
    version: int
    updated_at: datetime


class TorOut(TorSummary):
    project_id: UUID
    sections: list[TorSection]
    missing_information: list[str]
    review_comment: str
    submitted_at: datetime | None
    approved_at: datetime | None
    created_at: datetime


class TorVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version: int
    title: str
    note: str
    created_by: UUID | None
    created_at: datetime


class GenerateTorIn(BaseModel):
    instructions: str = Field(
        default="", max_length=2000, description="Précisions de l'utilisateur pour la rédaction"
    )
