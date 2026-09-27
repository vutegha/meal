"""reconnaissance de caracteres

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-27 22:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE document_status ADD VALUE IF NOT EXISTS 'ocr' BEFORE 'extracted'")


def downgrade() -> None:
    # PostgreSQL ne sait pas retirer une valeur d'énumération : on recrée le type.
    op.execute("UPDATE source_documents SET status = 'failed' WHERE status = 'ocr'")
    op.execute("ALTER TYPE document_status RENAME TO document_status_old")
    op.execute("CREATE TYPE document_status AS ENUM ('uploaded', 'extracted', 'failed')")
    op.execute("ALTER TABLE source_documents ALTER COLUMN status DROP DEFAULT")
    op.execute(
        "ALTER TABLE source_documents ALTER COLUMN status TYPE document_status "
        "USING status::text::document_status"
    )
    op.execute("DROP TYPE document_status_old")
