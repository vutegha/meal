"""cibles par periode et devises

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-27 23:50:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMPTY = sa.text("'[]'::jsonb")


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("exchange_rates", postgresql.JSONB(), nullable=False, server_default=EMPTY),
    )
    op.add_column(
        "indicators",
        sa.Column("period_targets", postgresql.JSONB(), nullable=False, server_default=EMPTY),
    )
    op.add_column(
        "expenses", sa.Column("currency", sa.String(3), nullable=False, server_default="")
    )
    op.add_column("expenses", sa.Column("original_amount", sa.Numeric(18, 2), nullable=True))
    op.add_column("expenses", sa.Column("exchange_rate", sa.Numeric(18, 6), nullable=True))


def downgrade() -> None:
    op.drop_column("expenses", "exchange_rate")
    op.drop_column("expenses", "original_amount")
    op.drop_column("expenses", "currency")
    op.drop_column("indicators", "period_targets")
    op.drop_column("projects", "exchange_rates")
