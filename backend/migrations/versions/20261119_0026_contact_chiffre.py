"""contact des plaignants chiffré

Le contact (nom, téléphone) des plaintes et retours est chiffré en base avec une clé dérivée de
SECRET_KEY ; `contact_index` garde l'empreinte (HMAC) des 9 derniers chiffres du numéro pour
retrouver une personne sans garder le numéro en clair. Les contacts existants sont chiffrés ici.

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-19 23:55:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.crypto import decrypt_field, encrypt_field, phone_index

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

entries = sa.table(
    "feedback_entries",
    sa.column("id", sa.Uuid),
    sa.column("contact", sa.Text),
    sa.column("contact_index", sa.String),
)


def upgrade() -> None:
    op.alter_column("feedback_entries", "contact", type_=sa.Text(), existing_type=sa.String(300))
    op.add_column(
        "feedback_entries",
        sa.Column("contact_index", sa.String(length=40), nullable=False, server_default=""),
    )
    op.alter_column("feedback_entries", "contact_index", server_default=None)
    op.create_index(
        op.f("ix_feedback_entries_contact_index"),
        "feedback_entries",
        ["contact_index"],
        unique=False,
    )
    # Migration avec le propriétaire des tables : la Row Level Security ne filtre rien ici.
    bind = op.get_bind()
    rows = bind.execute(
        sa.select(entries.c.id, entries.c.contact).where(entries.c.contact != "")
    ).all()
    for row in rows:
        plain = decrypt_field(row.contact)
        bind.execute(
            entries.update()
            .where(entries.c.id == row.id)
            .values(contact=encrypt_field(plain), contact_index=phone_index(plain))
        )


def downgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.select(entries.c.id, entries.c.contact).where(entries.c.contact != "")
    ).all()
    for row in rows:
        bind.execute(
            entries.update()
            .where(entries.c.id == row.id)
            .values(contact=decrypt_field(row.contact)[:300])
        )
    op.drop_index(op.f("ix_feedback_entries_contact_index"), table_name="feedback_entries")
    op.drop_column("feedback_entries", "contact_index")
    op.alter_column("feedback_entries", "contact", type_=sa.String(300), existing_type=sa.Text())
