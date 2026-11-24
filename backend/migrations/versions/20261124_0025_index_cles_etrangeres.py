"""index des clés étrangères et des tris courants

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-24 18:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Clés étrangères sans index : supprimer ou anonymiser un utilisateur (ON DELETE SET NULL)
# parcourait chacune de ces tables en entier.
FOREIGN_KEYS = (
    ("periodic_reports", "template_id"),
    ("periodic_reports", "created_by"),
    ("periodic_reports", "submitted_by"),
    ("periodic_reports", "approved_by"),
    ("periodic_report_versions", "created_by"),
    ("feedback_entries", "activity_id"),
    ("feedback_entries", "assigned_to"),
    ("feedback_entries", "created_by"),
    ("sms_messages", "sent_by"),
    ("lessons_learned", "activity_id"),
    ("lessons_learned", "source_report_id"),
    ("lessons_learned", "created_by"),
    ("source_documents", "uploaded_by"),
    ("jobs", "created_by"),
    ("ai_proposals", "job_id"),
    ("ai_proposals", "reviewed_by"),
    ("payments", "paid_by"),
    ("payments", "recorded_by"),
    ("activity_executions", "created_by"),
    ("evidence", "consent_recorded_by"),
    ("evidence", "uploaded_by"),
    ("collection_forms", "activity_id"),
    ("collection_forms", "created_by"),
    ("form_submissions", "submitted_by"),
    ("password_resets", "created_by"),
    ("audit_logs", "actor_id"),
    ("indicators", "owner_id"),
    ("indicator_values", "recorded_by"),
    ("narrative_reports", "template_id"),
    ("narrative_reports", "created_by"),
    ("narrative_reports", "submitted_by"),
    ("narrative_reports", "approved_by"),
    ("report_versions", "created_by"),
    ("document_templates", "created_by"),
    ("terms_of_reference", "template_id"),
    ("terms_of_reference", "created_by"),
    ("terms_of_reference", "submitted_by"),
    ("terms_of_reference", "approved_by"),
    ("tor_versions", "created_by"),
)

# Listes triées par date au sein d'un projet ou d'une organisation.
SORTED = (
    ("activity_executions", ("project_id", "start_date")),
    ("feedback_entries", ("project_id", "received_on")),
    ("audit_logs", ("organization_id", "created_at")),
)


def upgrade() -> None:
    for table, column in FOREIGN_KEYS:
        op.create_index(op.f(f"ix_{table}_{column}"), table, [column])
    for table, columns in SORTED:
        op.create_index(f"ix_{table}_{'_'.join(columns)}", table, list(columns))


def downgrade() -> None:
    for table, columns in reversed(SORTED):
        op.drop_index(f"ix_{table}_{'_'.join(columns)}", table_name=table)
    for table, column in reversed(FOREIGN_KEYS):
        op.drop_index(op.f(f"ix_{table}_{column}"), table_name=table)
