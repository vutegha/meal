from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

FieldType = Literal["text", "number", "integer", "select", "multiselect", "yesno", "date"]
FormStatus = Literal["draft", "published", "closed"]


class FormField(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9_]{1,40}$")
    label: str = Field(min_length=1, max_length=300)
    type: FieldType
    required: bool = False
    options: list[str] = Field(default_factory=list, max_length=50)
    hint: str = Field(default="", max_length=300)

    @model_validator(mode="after")
    def _options(self) -> "FormField":
        self.options = [o.strip() for o in self.options if o.strip()]
        if self.type in ("select", "multiselect"):
            if len(self.options) < 2:
                raise ValueError(f"« {self.label} » : au moins deux choix")
            if len(set(self.options)) != len(self.options):
                raise ValueError(f"« {self.label} » : choix en double")
        else:
            self.options = []
        return self


def _unique(fields: list[FormField]) -> list[FormField]:
    keys = [f.key for f in fields]
    if len(set(keys)) != len(keys):
        raise ValueError("Deux questions ont la même clé")
    return fields


class FormIn(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    description: str = Field(default="", max_length=4000)
    activity_id: UUID | None = None
    fields: list[FormField] = Field(min_length=1, max_length=100)

    _unique = field_validator("fields")(_unique)


class FormUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    activity_id: UUID | None = None
    fields: list[FormField] | None = Field(default=None, min_length=1, max_length=100)
    status: FormStatus | None = None

    @field_validator("fields")
    @classmethod
    def _unique_fields(cls, fields: list[FormField] | None) -> list[FormField] | None:
        return None if fields is None else _unique(fields)


class FormOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    title: str
    description: str
    status: FormStatus
    fields: list[FormField]
    activity_id: UUID | None
    created_at: datetime
    submissions: int = 0


class SubmissionIn(BaseModel):
    answers: dict[str, Any]
    location: str = Field(default="", max_length=300)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    collected_at: datetime | None = None
    client_uuid: UUID | None = None


class SubmissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    form_id: UUID
    answers: dict[str, Any]
    location: str
    latitude: float | None
    longitude: float | None
    collected_at: datetime
    submitted_by: UUID | None
    submitter_name: str = ""


class FieldSummary(BaseModel):
    key: str
    label: str
    type: FieldType
    answered: int
    # Choix : effectif par option ; oui/non : effectif de chaque réponse.
    counts: dict[str, int] = Field(default_factory=dict)
    # Nombres : total, moyenne, minimum, maximum.
    total: float | None = None
    mean: float | None = None
    min: float | None = None
    max: float | None = None
    # Texte : quelques réponses récentes.
    samples: list[str] = Field(default_factory=list)


class FormSummary(BaseModel):
    submissions: int
    fields: list[FieldSummary]
