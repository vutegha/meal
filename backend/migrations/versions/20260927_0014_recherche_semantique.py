"""recherche semantique

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-28 00:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Extension fournie par l'image pgvector/pgvector (docker-compose et CI).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column("document_pages", sa.Column("embedding", Vector(1024), nullable=True))
    op.create_index(
        "ix_document_pages_embedding",
        "document_pages",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_document_pages_embedding", table_name="document_pages")
    op.drop_column("document_pages", "embedding")
