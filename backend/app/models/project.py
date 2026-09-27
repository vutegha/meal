import enum
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, IdMixin, TimestampMixin


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class ProjectStatus(enum.StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    CLOSED = "closed"


class NodeLevel(enum.StrEnum):
    GOAL = "goal"
    OUTCOME = "outcome"
    OUTPUT = "output"
    ACTIVITY = "activity"
    SUB_ACTIVITY = "sub_activity"


# Niveau parent attendu pour chaque niveau du cadre logique.
PARENT_LEVEL: dict[NodeLevel, NodeLevel | None] = {
    NodeLevel.GOAL: None,
    NodeLevel.OUTCOME: NodeLevel.GOAL,
    NodeLevel.OUTPUT: NodeLevel.OUTCOME,
    NodeLevel.ACTIVITY: NodeLevel.OUTPUT,
    NodeLevel.SUB_ACTIVITY: NodeLevel.ACTIVITY,
}


class Aggregation(enum.StrEnum):
    SUM = "sum"
    LATEST = "latest"


class Project(IdMixin, TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("organization_id", "code"),)

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    donor: Mapped[str] = mapped_column(String(200), default="")
    start_date: Mapped[date | None]
    end_date: Mapped[date | None]
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    language: Mapped[str] = mapped_column(String(8), default="fr")
    status: Mapped[ProjectStatus] = mapped_column(
        _enum(ProjectStatus, "project_status"), default=ProjectStatus.DRAFT
    )
    zones: Mapped[list[str]] = mapped_column(JSONB, default=list)
    target_groups: Mapped[list[str]] = mapped_column(JSONB, default=list)


class LogframeNode(IdMixin, TimestampMixin, Base):
    __tablename__ = "logframe_nodes"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("logframe_nodes.id", ondelete="CASCADE"), index=True
    )
    level: Mapped[NodeLevel] = mapped_column(_enum(NodeLevel, "node_level"))
    code: Mapped[str] = mapped_column(String(40), default="")
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    assumptions: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[int] = mapped_column(default=0)


class BudgetLine(IdMixin, TimestampMixin, Base):
    __tablename__ = "budget_lines"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    # Nul pour les coûts de support non rattachés à une activité.
    activity_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("logframe_nodes.id", ondelete="SET NULL"), index=True
    )
    label: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(100), default="")
    donor_line_code: Mapped[str] = mapped_column(String(40), default="")
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    unit: Mapped[str] = mapped_column(String(40), default="")
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    frequency: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal(1))
    is_estimate: Mapped[bool] = mapped_column(default=False)

    expenses: Mapped[list["Expense"]] = relationship(
        back_populates="budget_line", cascade="all, delete-orphan"
    )

    @property
    def planned(self) -> Decimal:
        return (self.quantity * self.unit_cost * self.frequency).quantize(Decimal("0.01"))


class Expense(IdMixin, TimestampMixin, Base):
    __tablename__ = "expenses"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    budget_line_id: Mapped[UUID] = mapped_column(
        ForeignKey("budget_lines.id", ondelete="CASCADE"), index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    spent_on: Mapped[date]
    reference: Mapped[str] = mapped_column(String(100), default="")
    description: Mapped[str] = mapped_column(Text, default="")

    budget_line: Mapped[BudgetLine] = relationship(back_populates="expenses")


class Indicator(IdMixin, TimestampMixin, Base):
    __tablename__ = "indicators"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    node_id: Mapped[UUID] = mapped_column(
        ForeignKey("logframe_nodes.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(40), default="")
    name: Mapped[str] = mapped_column(Text)
    definition: Mapped[str] = mapped_column(Text, default="")
    unit: Mapped[str] = mapped_column(String(40), default="")
    baseline: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    target: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    aggregation: Mapped[Aggregation] = mapped_column(
        _enum(Aggregation, "aggregation"), default=Aggregation.SUM
    )
    disaggregations: Mapped[list[str]] = mapped_column(JSONB, default=list)
    source_of_verification: Mapped[str] = mapped_column(Text, default="")
    collection_method: Mapped[str] = mapped_column(Text, default="")
    frequency: Mapped[str] = mapped_column(String(40), default="")
    owner_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    values: Mapped[list["IndicatorValue"]] = relationship(
        back_populates="indicator",
        cascade="all, delete-orphan",
        order_by="IndicatorValue.period_end",
    )


class IndicatorValue(IdMixin, TimestampMixin, Base):
    __tablename__ = "indicator_values"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    indicator_id: Mapped[UUID] = mapped_column(
        ForeignKey("indicators.id", ondelete="CASCADE"), index=True
    )
    period_start: Mapped[date]
    period_end: Mapped[date]
    value: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    disaggregation: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    source: Mapped[str] = mapped_column(Text, default="")
    recorded_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    indicator: Mapped[Indicator] = relationship(back_populates="values")
