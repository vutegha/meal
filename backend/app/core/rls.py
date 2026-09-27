"""Row Level Security : chaque organisation ne voit que ses lignes, même en cas d'oubli de filtre.

L'API se connecte avec le rôle de la base (propriétaire des tables) puis bascule sur le rôle
`meal_app`, qui n'en est pas propriétaire et subit donc la RLS. Chaque transaction positionne
`app.current_org` (l'organisation de la requête) ; les tâches internes (worker, données de
démonstration) peuvent positionner `app.system`, jamais une requête HTTP.
"""

APP_ROLE = "meal_app"

# Tables qui portent `organization_id` et sont filtrées. `memberships` reste hors RLS : c'est
# elle qui permet de savoir à quelles organisations un utilisateur appartient.
TENANT_TABLES = (
    "audit_logs",
    "projects",
    "ai_calls",
    "jobs",
    "logframe_nodes",
    "periodic_reports",
    "periodic_report_versions",
    "source_documents",
    "document_pages",
    "activity_executions",
    "ai_proposals",
    "budget_lines",
    "feedback_entries",
    "indicators",
    "indicator_values",
    "terms_of_reference",
    "tor_versions",
    "evidence",
    "expenses",
    "narrative_reports",
    "report_versions",
    "lessons_learned",
    "document_templates",
)

POLICY = (
    "organization_id = nullif(current_setting('app.current_org', true), '')::uuid "
    "OR current_setting('app.system', true) = 'on'"
)


def role_statements(role: str = APP_ROLE) -> list[str]:
    return [
        f"""DO $$ BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN
                CREATE ROLE {role} NOLOGIN;
            END IF;
        END $$""",
        f"GRANT {role} TO CURRENT_USER",
        f"GRANT USAGE ON SCHEMA public TO {role}",
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}",
        f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {role}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {role}",
    ]


def enable_statements(table: str) -> list[str]:
    """À appeler dans la migration de toute nouvelle table portant `organization_id`."""
    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"DROP POLICY IF EXISTS tenant_isolation ON {table}",
        f"CREATE POLICY tenant_isolation ON {table} USING ({POLICY}) WITH CHECK ({POLICY})",
    ]


def disable_statements(table: str) -> list[str]:
    return [
        f"DROP POLICY IF EXISTS tenant_isolation ON {table}",
        f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY",
    ]


def all_statements() -> list[str]:
    statements = role_statements()
    for table in TENANT_TABLES:
        statements += enable_statements(table)
    return statements
