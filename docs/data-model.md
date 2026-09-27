# Modèle de données

Toutes les clés primaires sont des UUID. Les horodatages sont en UTC (`timestamptz`). Toute entité métier porte `organization_id` (tenancy). Les entités marquées *(étape N)* ne sont pas encore implémentées.

## Socle (étape 1)

| Entité | Champs principaux |
|---|---|
| `organizations` | id, name, slug (unique), default_language, created_at |
| `users` | id, email (unique, minuscules), full_name, password_hash, is_active, created_at |
| `memberships` | id, organization_id → organizations, user_id → users, role, created_at ; unique (organization_id, user_id) |
| `audit_logs` | id, organization_id, actor_id → users (nullable), action, entity_type, entity_id, data (jsonb), created_at |

## Projet et cadre logique (étape 2)

| Entité | Champs principaux |
|---|---|
| `projects` | id, organization_id, code, title, donor, start_date, end_date, currency, language, zones (jsonb), target_groups (jsonb), status |
| `logframe_nodes` | id, project_id, parent_id, level (`goal`, `outcome`, `output`, `activity`, `sub_activity`), code, title, description, assumptions, order ; arbre auto-référencé |
| `budget_lines` | id, project_id, activity_id → logframe_nodes, donor_line_code, label, quantity, unit, unit_cost, frequency, currency, is_estimate |
| `expenses` | id, budget_line_id, amount, currency, fx_rate, date, reference, execution_id (nullable) |
| `exchange_rates` | id, organization_id, from_currency, to_currency, rate, valid_on |
| `indicators` | id, project_id, node_id → logframe_nodes, code, name, definition, formula, unit, disaggregations (jsonb), baseline, source_of_verification, collection_method, frequency, owner_id → users |
| `indicator_targets` | id, indicator_id, period_start, period_end, value, disaggregation (jsonb) |
| `indicator_values` | id, indicator_id, period_start, period_end, value, disaggregation (jsonb), execution_id (nullable), source_ref |

## Documents et IA (étape 3)

| Entité | Champs principaux |
|---|---|
| `source_documents` | id, project_id, filename, kind, storage_key, sha256 (unique par projet), size_bytes, page_count, text_chars, status (`uploaded`, `extracted`, `failed`), error |
| `document_pages` | id, document_id, number, text, search (`tsvector` français calculé, index GIN) |
| `ai_proposals` | id, project_id, job_id, kind (`logframe`), payload (jsonb : éléments proposés, citations, vérification), status (`pending`, `applied`, `rejected`), reviewed_by, reviewed_at |
| `ai_calls` | id, organization_id, project_id, purpose, prompt_version, model, jetons (entrée, sortie, cache), cost_usd, duration_ms, status, error |
| `jobs` | id, organization_id, project_id, kind, params (jsonb), status (`queued`, `running`, `succeeded`, `failed`), result (jsonb), error |

## TdR, exécution, rapports (étapes 4 à 6)

| Entité | Champs principaux |
|---|---|
| `terms_of_reference` | id, project_id, activity_id (unique), title, status (`draft`, `submitted`, `approved`), sections (jsonb : clé, titre, contenu Markdown), missing_information, version, review_comment, submitted_by/at, approved_by/at |
| `tor_versions` | id, tor_id, version, title, sections, note, created_by |
| `document_templates` (à venir) | id, organization_id, kind (`tor`, `activity_report`, `periodic_report`), structure (jsonb) |
| `activity_executions` | id, project_id, activity_id, title, start_date, end_date, location, latitude, longitude, participants (jsonb : women, men, girls, boys, with_disability), notes, status (`in_progress`, `completed`), client_uuid (unique, idempotence hors ligne) |
| `evidence` | id, execution_id, kind (`photo`, `report`, `minutes`, `attendance`, `other`), filename, content_type, sha256, storage_key, thumbnail_key, caption, taken_at et latitude/longitude (EXIF), consent_given, text (extrait des documents), page_count, uploaded_by, client_uuid |
| `expenses.execution_id` | rattache une dépense réelle à l'exécution qui l'a occasionnée |
| `narrative_reports` | id, execution_id, version, status, content (jsonb), citations (jsonb), missing_info (jsonb), approved_by |
| `periodic_reports` | id, project_id, period_start, period_end, kind, content (jsonb), status |

## Redevabilité et apprentissage (étape 7)

| Entité | Champs principaux |
|---|---|
| `feedback_entries` | id, project_id, channel, category, sensitivity, description, status, received_at, responded_at, assigned_to |
| `lessons_learned` | id, project_id, source_report_id, title, description, tags (jsonb) |
