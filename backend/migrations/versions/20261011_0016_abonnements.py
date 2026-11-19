"""abonnements et paiements

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-11 15:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core import rls

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:  # type: ignore[type-arg]
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("plan", sa.String(length=40), nullable=False),
        sa.Column("cycle", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_subscriptions_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscriptions")),
        sa.UniqueConstraint("organization_id", name=op.f("uq_subscriptions_organization_id")),
    )
    op.create_table(
        "payments",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("plan", sa.String(length=40), nullable=False),
        sa.Column("cycle", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("reference", sa.String(length=80), nullable=False),
        sa.Column("paid_by", sa.Uuid(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_payments_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["paid_by"], ["users.id"], name=op.f("fk_payments_paid_by_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
    )
    op.create_index(
        op.f("ix_payments_organization_id"), "payments", ["organization_id"], unique=False
    )
    for statement in rls.enable_statements("payments"):
        op.execute(statement)
    # Les organisations existantes gardent toutes leurs fonctions : formule Institution offerte
    # pour un an, visible et modifiable depuis leur page Abonnement.
    op.execute(
        """INSERT INTO subscriptions (id, organization_id, plan, cycle, status,
               current_period_end, credits, cancel_at_period_end)
           SELECT gen_random_uuid(), id, 'institution', 'annual', 'active',
               now() + interval '1 year', 0, false
           FROM organizations"""
    )


def downgrade() -> None:
    for statement in rls.disable_statements("payments"):
        op.execute(statement)
    op.drop_index(op.f("ix_payments_organization_id"), table_name="payments")
    op.drop_table("payments")
    op.drop_table("subscriptions")
