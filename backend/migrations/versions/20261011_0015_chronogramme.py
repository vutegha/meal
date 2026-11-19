"""chronogramme des activites

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-11 13:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("logframe_nodes", sa.Column("planned_start", sa.Date(), nullable=True))
    op.add_column("logframe_nodes", sa.Column("planned_end", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("logframe_nodes", "planned_end")
    op.drop_column("logframe_nodes", "planned_start")
