from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

TemplateKind = Literal["tor", "report", "periodic"]


class TemplateSection(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9_]{1,40}$")
    title: str = Field(min_length=1, max_length=200)
    # Consigne transmise à l'IA pour cette section (ton, longueur, contenu attendu).
    guidance: str = Field(default="", max_length=1000)


class TemplateLayout(BaseModel):
    header: str = Field(default="", max_length=200)
    footer: str = Field(default="", max_length=200)
    color: str = Field(default="#0f5b52", pattern=r"^#[0-9a-fA-F]{6}$")


class TemplateIn(BaseModel):
    kind: TemplateKind
    name: str = Field(min_length=2, max_length=200)
    donor: str = Field(default="", max_length=200)
    is_default: bool = False
    sections: list[TemplateSection] = Field(min_length=1, max_length=30)
    layout: TemplateLayout = Field(default_factory=TemplateLayout)

    @field_validator("sections")
    @classmethod
    def _unique_keys(cls, sections: list[TemplateSection]) -> list[TemplateSection]:
        keys = [s.key for s in sections]
        if len(set(keys)) != len(keys):
            raise ValueError("Deux sections ont la même clé")
        return sections

    @field_validator("donor", "name")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    donor: str | None = Field(default=None, max_length=200)
    is_default: bool | None = None
    sections: list[TemplateSection] | None = Field(default=None, min_length=1, max_length=30)
    layout: TemplateLayout | None = None

    @field_validator("sections")
    @classmethod
    def _unique_keys(cls, sections: list[TemplateSection] | None) -> list[TemplateSection] | None:
        return None if sections is None else TemplateIn._unique_keys(sections)


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: TemplateKind
    name: str
    donor: str
    is_default: bool
    sections: list[TemplateSection]
    layout: TemplateLayout
    created_at: datetime


class BuiltinSection(BaseModel):
    key: str
    title: str
    # Rempli par l'application (tableau calculé), jamais rédigé par l'IA.
    computed: bool


class BuiltinTemplates(BaseModel):
    tor: list[BuiltinSection]
    report: list[BuiltinSection]
    periodic: list[BuiltinSection]
