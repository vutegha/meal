"""row level security

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-27 21:00:00
"""

from collections.abc import Sequence

from alembic import op

from app.core import rls

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for statement in rls.all_statements():
        op.execute(statement)


def downgrade() -> None:
    for table in rls.TENANT_TABLES:
        for statement in rls.disable_statements(table):
            op.execute(statement)
    op.execute(f"DROP OWNED BY {rls.APP_ROLE}")
    # Le rôle est commun au serveur : on le garde s'il sert encore dans une autre base.
    op.execute(
        f"""DO $$ BEGIN
            DROP ROLE IF EXISTS {rls.APP_ROLE};
        EXCEPTION WHEN dependent_objects_still_exist THEN NULL;
        END $$"""
    )
