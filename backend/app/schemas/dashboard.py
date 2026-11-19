from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

Beneficiary = Literal["women", "men", "girls", "boys", "with_disability"]


class DashboardProject(BaseModel):
    id: UUID
    code: str
    title: str


class DashboardOptions(BaseModel):
    years: list[int]
    zones: list[str]
    locations: list[str]
    projects: list[DashboardProject]


class People(BaseModel):
    women: int = 0
    men: int = 0
    girls: int = 0
    boys: int = 0
    with_disability: int = 0
    total: int = 0
    # Effectifs de 1 à 4 cachés (remis à 0) dans une vue restreinte : voir services/dashboard.py.
    masked: list[str] = Field(default_factory=list)


class Breakdown(BaseModel):
    """Une ligne de ventilation : un mois, un lieu, une zone ou un projet."""

    key: str
    label: str
    executions: int = 0
    people: int = 0
    # Effectif de 1 à 4 caché (people vaut alors 0).
    masked: bool = False


class Spending(BaseModel):
    currency: str
    amount: Decimal


class OrgDashboard(BaseModel):
    options: DashboardOptions
    projects: int
    active_projects: int
    executions: int
    completed_executions: int
    people: People
    spending: list[Spending]
    by_month: list[Breakdown]
    by_location: list[Breakdown]
    by_zone: list[Breakdown]
    by_project: list[Breakdown]
