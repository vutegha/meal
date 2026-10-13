"""statut, moyen et reçu des paiements

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-13 16:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "payments", sa.Column("status", sa.String(20), server_default="paid", nullable=False)
    )
    op.add_column(
        "payments", sa.Column("method", sa.String(30), server_default="online", nullable=False)
    )
    op.add_column("payments", sa.Column("receipt_number", sa.String(30), nullable=True))
    op.add_column("payments", sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("payments", sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("payments", sa.Column("note", sa.String(500), server_default="", nullable=False))
    op.add_column("payments", sa.Column("recorded_by", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_payments_recorded_by_users"),
        "payments",
        "users",
        ["recorded_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        op.f("uq_payments_receipt_number"), "payments", ["receipt_number"]
    )
    # Numérotation continue des reçus, toutes organisations confondues.
    op.execute("CREATE SEQUENCE payment_receipt_seq")
    # Les paiements déjà enregistrés ont été encaissés : ils reçoivent leur numéro dans l'ordre.
    op.execute(
        """UPDATE payments p SET paid_at = p.created_at,
               receipt_number = 'WM-' || to_char(p.created_at, 'YYYY') || '-'
                   || lpad(n.seq::text, 6, '0')
           FROM (SELECT id, nextval('payment_receipt_seq') AS seq
                 FROM (SELECT id FROM payments ORDER BY created_at, id) ordered) n
           WHERE n.id = p.id"""
    )


def downgrade() -> None:
    op.execute("DROP SEQUENCE payment_receipt_seq")
    op.drop_constraint(op.f("uq_payments_receipt_number"), "payments", type_="unique")
    op.drop_constraint(op.f("fk_payments_recorded_by_users"), "payments", type_="foreignkey")
    for column in ("recorded_by", "note", "refunded_at", "paid_at", "receipt_number", "method"):
        op.drop_column("payments", column)
    op.drop_column("payments", "status")
