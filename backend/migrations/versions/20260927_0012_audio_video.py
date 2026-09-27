"""preuves audio et video

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-27 23:30:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE evidence_kind ADD VALUE IF NOT EXISTS 'audio' BEFORE 'other'")
    op.execute("ALTER TYPE evidence_kind ADD VALUE IF NOT EXISTS 'video' BEFORE 'other'")


def downgrade() -> None:
    # PostgreSQL ne sait pas retirer une valeur d'énumération : on recrée le type.
    op.execute("UPDATE evidence SET kind = 'other' WHERE kind IN ('audio', 'video')")
    op.execute("ALTER TYPE evidence_kind RENAME TO evidence_kind_old")
    op.execute(
        "CREATE TYPE evidence_kind AS ENUM ('report', 'minutes', 'attendance', 'photo', 'other')"
    )
    op.execute(
        "ALTER TABLE evidence ALTER COLUMN kind TYPE evidence_kind USING kind::text::evidence_kind"
    )
    op.execute("DROP TYPE evidence_kind_old")
