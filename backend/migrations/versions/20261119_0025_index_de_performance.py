"""index de performance

Index des clés étrangères vers les utilisateurs (effacement RGPD d'un compte sans parcourir
chaque table), index des listes paginées et des valeurs totales des indicateurs, index
trigrammes pour la recherche d'une personne dans le registre des plaintes.

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-19 23:23:13.681715
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    # Statistiques par requête (actives avec shared_preload_libraries, voir docker-compose.yml).
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
    op.create_index(
        op.f("ix_activity_executions_created_by"),
        "activity_executions",
        ["created_by"],
        unique=False,
    )
    op.create_index(
        "ix_activity_executions_project_recent",
        "activity_executions",
        ["project_id", "start_date", "created_at"],
        unique=False,
    )
    op.create_index(op.f("ix_ai_proposals_job_id"), "ai_proposals", ["job_id"], unique=False)
    op.create_index(
        op.f("ix_ai_proposals_reviewed_by"), "ai_proposals", ["reviewed_by"], unique=False
    )
    op.create_index(op.f("ix_audit_logs_actor_id"), "audit_logs", ["actor_id"], unique=False)
    op.create_index(
        "ix_audit_logs_org_recent", "audit_logs", ["organization_id", "created_at"], unique=False
    )
    op.create_index(
        op.f("ix_collection_forms_activity_id"), "collection_forms", ["activity_id"], unique=False
    )
    op.create_index(
        op.f("ix_collection_forms_created_by"), "collection_forms", ["created_by"], unique=False
    )
    op.create_index(
        op.f("ix_document_templates_created_by"), "document_templates", ["created_by"], unique=False
    )
    op.create_index(
        op.f("ix_evidence_consent_recorded_by"), "evidence", ["consent_recorded_by"], unique=False
    )
    op.create_index(op.f("ix_evidence_uploaded_by"), "evidence", ["uploaded_by"], unique=False)
    op.create_index(
        op.f("ix_feedback_entries_activity_id"), "feedback_entries", ["activity_id"], unique=False
    )
    op.create_index(
        op.f("ix_feedback_entries_assigned_to"), "feedback_entries", ["assigned_to"], unique=False
    )
    op.create_index(
        op.f("ix_feedback_entries_created_by"), "feedback_entries", ["created_by"], unique=False
    )
    op.create_index(
        "ix_feedback_entries_description_trgm",
        "feedback_entries",
        ["description"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"description": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_feedback_entries_project_recent",
        "feedback_entries",
        ["project_id", "received_on"],
        unique=False,
    )
    op.create_index(
        op.f("ix_form_submissions_submitted_by"), "form_submissions", ["submitted_by"], unique=False
    )
    op.create_index(
        op.f("ix_indicator_values_recorded_by"), "indicator_values", ["recorded_by"], unique=False
    )
    op.create_index(
        "ix_indicator_values_totals",
        "indicator_values",
        ["indicator_id", "period_end"],
        unique=False,
        postgresql_where=sa.text("disaggregation = '{}'::jsonb"),
    )
    op.create_index(op.f("ix_indicators_owner_id"), "indicators", ["owner_id"], unique=False)
    op.create_index(op.f("ix_jobs_created_by"), "jobs", ["created_by"], unique=False)
    op.create_index(
        op.f("ix_lessons_learned_activity_id"), "lessons_learned", ["activity_id"], unique=False
    )
    op.create_index(
        op.f("ix_lessons_learned_created_by"), "lessons_learned", ["created_by"], unique=False
    )
    op.create_index(
        op.f("ix_lessons_learned_source_report_id"),
        "lessons_learned",
        ["source_report_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_narrative_reports_approved_by"), "narrative_reports", ["approved_by"], unique=False
    )
    op.create_index(
        op.f("ix_narrative_reports_created_by"), "narrative_reports", ["created_by"], unique=False
    )
    op.create_index(
        op.f("ix_narrative_reports_submitted_by"),
        "narrative_reports",
        ["submitted_by"],
        unique=False,
    )
    op.create_index(
        op.f("ix_narrative_reports_template_id"), "narrative_reports", ["template_id"], unique=False
    )
    op.create_index(
        op.f("ix_password_resets_created_by"), "password_resets", ["created_by"], unique=False
    )
    op.create_index(op.f("ix_payments_paid_by"), "payments", ["paid_by"], unique=False)
    op.create_index(op.f("ix_payments_recorded_by"), "payments", ["recorded_by"], unique=False)
    op.create_index(
        op.f("ix_periodic_report_versions_created_by"),
        "periodic_report_versions",
        ["created_by"],
        unique=False,
    )
    op.create_index(
        op.f("ix_periodic_reports_approved_by"), "periodic_reports", ["approved_by"], unique=False
    )
    op.create_index(
        op.f("ix_periodic_reports_created_by"), "periodic_reports", ["created_by"], unique=False
    )
    op.create_index(
        op.f("ix_periodic_reports_submitted_by"), "periodic_reports", ["submitted_by"], unique=False
    )
    op.create_index(
        op.f("ix_periodic_reports_template_id"), "periodic_reports", ["template_id"], unique=False
    )
    op.create_index(
        op.f("ix_report_versions_created_by"), "report_versions", ["created_by"], unique=False
    )
    op.create_index(op.f("ix_sms_messages_sent_by"), "sms_messages", ["sent_by"], unique=False)
    op.create_index(
        op.f("ix_source_documents_uploaded_by"), "source_documents", ["uploaded_by"], unique=False
    )
    op.create_index(
        op.f("ix_terms_of_reference_approved_by"),
        "terms_of_reference",
        ["approved_by"],
        unique=False,
    )
    op.create_index(
        op.f("ix_terms_of_reference_created_by"), "terms_of_reference", ["created_by"], unique=False
    )
    op.create_index(
        op.f("ix_terms_of_reference_submitted_by"),
        "terms_of_reference",
        ["submitted_by"],
        unique=False,
    )
    op.create_index(
        op.f("ix_terms_of_reference_template_id"),
        "terms_of_reference",
        ["template_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tor_versions_created_by"), "tor_versions", ["created_by"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_tor_versions_created_by"), table_name="tor_versions")
    op.drop_index(op.f("ix_terms_of_reference_template_id"), table_name="terms_of_reference")
    op.drop_index(op.f("ix_terms_of_reference_submitted_by"), table_name="terms_of_reference")
    op.drop_index(op.f("ix_terms_of_reference_created_by"), table_name="terms_of_reference")
    op.drop_index(op.f("ix_terms_of_reference_approved_by"), table_name="terms_of_reference")
    op.drop_index(op.f("ix_source_documents_uploaded_by"), table_name="source_documents")
    op.drop_index(op.f("ix_sms_messages_sent_by"), table_name="sms_messages")
    op.drop_index(op.f("ix_report_versions_created_by"), table_name="report_versions")
    op.drop_index(op.f("ix_periodic_reports_template_id"), table_name="periodic_reports")
    op.drop_index(op.f("ix_periodic_reports_submitted_by"), table_name="periodic_reports")
    op.drop_index(op.f("ix_periodic_reports_created_by"), table_name="periodic_reports")
    op.drop_index(op.f("ix_periodic_reports_approved_by"), table_name="periodic_reports")
    op.drop_index(
        op.f("ix_periodic_report_versions_created_by"), table_name="periodic_report_versions"
    )
    op.drop_index(op.f("ix_payments_recorded_by"), table_name="payments")
    op.drop_index(op.f("ix_payments_paid_by"), table_name="payments")
    op.drop_index(op.f("ix_password_resets_created_by"), table_name="password_resets")
    op.drop_index(op.f("ix_narrative_reports_template_id"), table_name="narrative_reports")
    op.drop_index(op.f("ix_narrative_reports_submitted_by"), table_name="narrative_reports")
    op.drop_index(op.f("ix_narrative_reports_created_by"), table_name="narrative_reports")
    op.drop_index(op.f("ix_narrative_reports_approved_by"), table_name="narrative_reports")
    op.drop_index(op.f("ix_lessons_learned_source_report_id"), table_name="lessons_learned")
    op.drop_index(op.f("ix_lessons_learned_created_by"), table_name="lessons_learned")
    op.drop_index(op.f("ix_lessons_learned_activity_id"), table_name="lessons_learned")
    op.drop_index(op.f("ix_jobs_created_by"), table_name="jobs")
    op.drop_index(op.f("ix_indicators_owner_id"), table_name="indicators")
    op.drop_index(
        "ix_indicator_values_totals",
        table_name="indicator_values",
        postgresql_where=sa.text("disaggregation = '{}'::jsonb"),
    )
    op.drop_index(op.f("ix_indicator_values_recorded_by"), table_name="indicator_values")
    op.drop_index(op.f("ix_form_submissions_submitted_by"), table_name="form_submissions")
    op.drop_index("ix_feedback_entries_project_recent", table_name="feedback_entries")
    op.drop_index(
        "ix_feedback_entries_description_trgm",
        table_name="feedback_entries",
        postgresql_using="gin",
        postgresql_ops={"description": "gin_trgm_ops"},
    )
    op.drop_index(op.f("ix_feedback_entries_created_by"), table_name="feedback_entries")
    op.drop_index(op.f("ix_feedback_entries_assigned_to"), table_name="feedback_entries")
    op.drop_index(op.f("ix_feedback_entries_activity_id"), table_name="feedback_entries")
    op.drop_index(op.f("ix_evidence_uploaded_by"), table_name="evidence")
    op.drop_index(op.f("ix_evidence_consent_recorded_by"), table_name="evidence")
    op.drop_index(op.f("ix_document_templates_created_by"), table_name="document_templates")
    op.drop_index(op.f("ix_collection_forms_created_by"), table_name="collection_forms")
    op.drop_index(op.f("ix_collection_forms_activity_id"), table_name="collection_forms")
    op.drop_index("ix_audit_logs_org_recent", table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_actor_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_ai_proposals_reviewed_by"), table_name="ai_proposals")
    op.drop_index(op.f("ix_ai_proposals_job_id"), table_name="ai_proposals")
    op.drop_index("ix_activity_executions_project_recent", table_name="activity_executions")
    op.drop_index(op.f("ix_activity_executions_created_by"), table_name="activity_executions")
    op.execute("DROP EXTENSION IF EXISTS pg_stat_statements")
