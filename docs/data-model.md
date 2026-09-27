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
| `source_documents` | id, project_id, filename, mime_type, storage_key, sha256, page_count, status |
| `document_chunks` | id, document_id, page, position, text, embedding (`vector`) |
| `ai_proposals` | id, project_id, kind (`logframe`, `budget`, `indicator`), payload (jsonb), citations (jsonb), status (`pending`, `accepted`, `edited`, `rejected`), reviewed_by, reviewed_at |
| `ai_calls` | id, organization_id, purpose, model, input_tokens, output_tokens, cost, duration_ms, status, created_at |
| `jobs` | id, organization_id, kind, status, progress, result (jsonb), error |

## TdR, exécution, rapports (étapes 4 à 6)

| Entité | Champs principaux |
|---|---|
| `document_templates` | id, organization_id, kind (`tor`, `activity_report`, `periodic_report`), storage_key, structure (jsonb) |
| `terms_of_reference` | id, activity_id, version, status (`draft`, `in_review`, `approved`), content (jsonb TipTap), generated_by_ai, approved_by, approved_at |
| `activity_executions` | id, activity_id, start_date, end_date, location, geo (jsonb), participants (jsonb désagrégé), notes, status |
| `evidence_files` | id, execution_id, kind (`report`, `minutes`, `attendance`, `photo`, `audio`, `video`, `data`, `other`), storage_key, mime_type, exif (jsonb), consent_given, faces_blurred, caption, uploaded_by, client_uuid (idempotence hors ligne) |
| `narrative_reports` | id, execution_id, version, status, content (jsonb), citations (jsonb), missing_info (jsonb), approved_by |
| `periodic_reports` | id, project_id, period_start, period_end, kind, content (jsonb), status |

## Redevabilité et apprentissage (étape 7)

| Entité | Champs principaux |
|---|---|
| `feedback_entries` | id, project_id, channel, category, sensitivity, description, status, received_at, responded_at, assigned_to |
| `lessons_learned` | id, project_id, source_report_id, title, description, tags (jsonb) |
