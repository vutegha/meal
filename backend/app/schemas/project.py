from datetime import date, datetime
from decimal import Decimal
from typing import Any, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import Aggregation, NodeLevel, ProjectStatus


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _check_dates(start: date | None, end: date | None) -> None:
    if start and end and end < start:
        raise ValueError("La date de fin doit suivre la date de début")


# --- Projets ---------------------------------------------------------------


class ExchangeRate(BaseModel):
    """1 unité de `currency` vaut `rate` unités de la devise du projet, à partir de `valid_from`."""

    currency: str = Field(pattern="^[A-Z]{3}$")
    rate: Decimal = Field(gt=0, max_digits=18, decimal_places=6)
    valid_from: date


class ProjectIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=2, max_length=300)
    description: str = ""
    donor: str = Field(default="", max_length=200)
    start_date: date | None = None
    end_date: date | None = None
    currency: str = Field(default="USD", pattern="^[A-Z]{3}$")
    language: str = Field(default="fr", pattern="^(fr|en)$")
    status: ProjectStatus = ProjectStatus.DRAFT
    zones: list[str] = []
    target_groups: list[str] = []

    @model_validator(mode="after")
    def dates(self) -> Self:
        _check_dates(self.start_date, self.end_date)
        return self


class ProjectUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=40)
    title: str | None = Field(default=None, min_length=2, max_length=300)
    description: str | None = None
    donor: str | None = Field(default=None, max_length=200)
    start_date: date | None = None
    end_date: date | None = None
    currency: str | None = Field(default=None, pattern="^[A-Z]{3}$")
    language: str | None = Field(default=None, pattern="^(fr|en)$")
    status: ProjectStatus | None = None
    zones: list[str] | None = None
    target_groups: list[str] | None = None


class ProjectOut(ORMModel):
    id: UUID
    code: str
    title: str
    description: str
    donor: str
    start_date: date | None
    end_date: date | None
    currency: str
    language: str
    status: ProjectStatus
    zones: list[str]
    target_groups: list[str]
    exchange_rates: list[ExchangeRate] = []
    created_at: datetime


# --- Cadre logique --------------------------------------------------------


class NodeIn(BaseModel):
    parent_id: UUID | None = None
    level: NodeLevel
    code: str = Field(default="", max_length=40)
    title: str = Field(min_length=1)
    description: str = ""
    assumptions: str = ""
    position: int | None = None


class NodeUpdate(BaseModel):
    code: str | None = Field(default=None, max_length=40)
    title: str | None = Field(default=None, min_length=1)
    description: str | None = None
    assumptions: str | None = None
    position: int | None = None


class NodeOut(ORMModel):
    id: UUID
    parent_id: UUID | None
    level: NodeLevel
    code: str
    title: str
    description: str
    assumptions: str
    position: int


class NodeTree(NodeOut):
    children: list["NodeTree"] = []


# --- Budget -----------------------------------------------------------------


class BudgetLineIn(BaseModel):
    activity_id: UUID | None = None
    label: str = Field(min_length=1, max_length=300)
    category: str = Field(default="", max_length=100)
    donor_line_code: str = Field(default="", max_length=40)
    quantity: Decimal = Field(ge=0)
    unit: str = Field(default="", max_length=40)
    unit_cost: Decimal = Field(ge=0)
    frequency: Decimal = Field(default=Decimal(1), ge=0)
    is_estimate: bool = False


class BudgetLineUpdate(BaseModel):
    activity_id: UUID | None = None
    label: str | None = Field(default=None, min_length=1, max_length=300)
    category: str | None = Field(default=None, max_length=100)
    donor_line_code: str | None = Field(default=None, max_length=40)
    quantity: Decimal | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=40)
    unit_cost: Decimal | None = Field(default=None, ge=0)
    frequency: Decimal | None = Field(default=None, ge=0)
    is_estimate: bool | None = None


class BudgetLineOut(ORMModel):
    id: UUID
    activity_id: UUID | None
    label: str
    category: str
    donor_line_code: str
    quantity: Decimal
    unit: str
    unit_cost: Decimal
    frequency: Decimal
    is_estimate: bool
    planned: Decimal
    spent: Decimal = Decimal(0)


class ExpenseIn(BaseModel):
    # Montant dans `currency` (devise du projet si vide).
    amount: Decimal = Field(gt=0)
    spent_on: date
    reference: str = Field(default="", max_length=100)
    description: str = ""
    currency: str = Field(default="", pattern="^([A-Z]{3})?$")
    # Taux appliqué ; à défaut, celui du projet en vigueur à la date de la dépense.
    exchange_rate: Decimal | None = Field(default=None, gt=0)


class ExpenseOut(ORMModel):
    id: UUID
    budget_line_id: UUID
    # Montant dans la devise du projet.
    amount: Decimal
    spent_on: date
    reference: str
    description: str
    currency: str = ""
    original_amount: Decimal | None = None
    exchange_rate: Decimal | None = None


class ActivityBudget(BaseModel):
    activity_id: UUID | None
    code: str
    title: str
    planned: Decimal
    spent: Decimal
    execution_rate: float | None


class BudgetSummary(BaseModel):
    currency: str
    planned: Decimal
    spent: Decimal
    execution_rate: float | None
    over_budget_lines: int
    by_activity: list[ActivityBudget]


# --- Indicateurs -----------------------------------------------------------


class PeriodTarget(BaseModel):
    period_start: date
    period_end: date
    target: Decimal

    @model_validator(mode="after")
    def dates(self) -> Self:
        _check_dates(self.period_start, self.period_end)
        return self


class PeriodProgress(PeriodTarget):
    achieved: Decimal | None = None
    achievement_rate: float | None = None


def _sorted_targets(targets: list[PeriodTarget] | None) -> list[PeriodTarget] | None:
    if targets is None:
        return None
    targets = sorted(targets, key=lambda t: t.period_start)
    for previous, current in zip(targets, targets[1:], strict=False):
        if current.period_start <= previous.period_end:
            raise ValueError("Les périodes des cibles ne doivent pas se chevaucher")
    return targets


class IndicatorIn(BaseModel):
    node_id: UUID
    code: str = Field(default="", max_length=40)
    name: str = Field(min_length=2)
    definition: str = ""
    unit: str = Field(default="", max_length=40)
    baseline: Decimal | None = None
    target: Decimal | None = None
    aggregation: Aggregation = Aggregation.SUM
    disaggregations: list[str] = []
    source_of_verification: str = ""
    collection_method: str = ""
    frequency: str = Field(default="", max_length=40)
    owner_id: UUID | None = None
    period_targets: list[PeriodTarget] = Field(default=[], max_length=60)

    _targets = field_validator("period_targets")(_sorted_targets)


class IndicatorUpdate(BaseModel):
    node_id: UUID | None = None
    code: str | None = Field(default=None, max_length=40)
    name: str | None = Field(default=None, min_length=2)
    definition: str | None = None
    unit: str | None = Field(default=None, max_length=40)
    baseline: Decimal | None = None
    target: Decimal | None = None
    aggregation: Aggregation | None = None
    disaggregations: list[str] | None = None
    source_of_verification: str | None = None
    collection_method: str | None = None
    frequency: str | None = Field(default=None, max_length=40)
    owner_id: UUID | None = None
    period_targets: list[PeriodTarget] | None = Field(default=None, max_length=60)

    _targets = field_validator("period_targets")(_sorted_targets)


class IndicatorOut(ORMModel):
    id: UUID
    node_id: UUID
    code: str
    name: str
    definition: str
    unit: str
    baseline: Decimal | None
    target: Decimal | None
    aggregation: Aggregation
    disaggregations: list[str]
    source_of_verification: str
    collection_method: str
    frequency: str
    owner_id: UUID | None
    achieved: Decimal | None = None
    achievement_rate: float | None = None
    # Cibles intermédiaires avec la valeur atteinte sur chaque période.
    period_targets: list[PeriodProgress] = []


class IndicatorValueIn(BaseModel):
    period_start: date
    period_end: date
    value: Decimal
    disaggregation: dict[str, Any] = {}
    source: str = ""

    @model_validator(mode="after")
    def dates(self) -> Self:
        _check_dates(self.period_start, self.period_end)
        return self


class IndicatorValueOut(ORMModel):
    id: UUID
    indicator_id: UUID
    period_start: date
    period_end: date
    value: Decimal
    disaggregation: dict[str, Any]
    source: str
    recorded_by: UUID | None


class LogframeCheck(BaseModel):
    """Contrôles de cohérence du cadre logique."""

    nodes_without_indicator: list[NodeOut]
    indicators_without_source: list[IndicatorOut]
    activities_without_budget: list[NodeOut]
