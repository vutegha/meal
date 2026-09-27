import { type Tokens, tokenStore } from "./tokens";

export type Role =
  "admin" | "project_manager" | "meal_officer" | "field_agent" | "finance" | "viewer";

export const ROLES: Role[] = [
  "admin",
  "project_manager",
  "meal_officer",
  "field_agent",
  "finance",
  "viewer",
];

export interface Organization {
  id: string;
  name: string;
  slug: string;
  default_language: string;
  created_at: string;
  role: Role;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
}

export interface Me extends User {
  organizations: Organization[];
}

export interface Member {
  id: string;
  role: Role;
  user: User;
  created_at: string;
}

export interface AuditEntry {
  id: string;
  actor_id: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  data: Record<string, unknown>;
  created_at: string;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

const BASE = "/api/v1";

async function send(path: string, init: RequestInit, token?: string): Promise<Response> {
  const headers = new Headers(init.headers);
  if (typeof init.body === "string") headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(`${BASE}${path}`, { ...init, headers });
}

let refreshing: Promise<Tokens | null> | null = null;

async function refreshTokens(): Promise<Tokens | null> {
  const tokens = tokenStore.get();
  if (!tokens) return null;
  refreshing ??= send("/auth/refresh", {
    method: "POST",
    body: JSON.stringify({ refresh_token: tokens.refresh_token }),
  })
    .then(async (r) => (r.ok ? ((await r.json()) as Tokens) : null))
    .catch(() => null)
    .finally(() => {
      refreshing = null;
    });
  const fresh = await refreshing;
  tokenStore.set(fresh);
  return fresh;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // corps non JSON
  }
  return response.statusText;
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response = await send(path, init, tokenStore.get()?.access_token);
  if (response.status === 401 && tokenStore.get()) {
    const fresh = await refreshTokens();
    if (fresh) response = await send(path, init, fresh.access_token);
  }
  if (!response.ok) throw new ApiError(response.status, await errorMessage(response));
  return (response.status === 204 ? undefined : await response.json()) as T;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  body: JSON.stringify(body),
});

export const api = {
  login: (email: string, password: string) =>
    request<Tokens>("/auth/login", json("POST", { email, password })),
  register: (body: {
    email: string;
    full_name: string;
    password: string;
    organization_name: string;
  }) => request<Tokens>("/auth/register", json("POST", body)),
  me: () => request<Me>("/auth/me"),
  createOrganization: (name: string) => request<Organization>("/orgs", json("POST", { name })),
  members: (orgId: string) => request<Member[]>(`/orgs/${orgId}/members`),
  addMember: (
    orgId: string,
    body: { email: string; role: Role; full_name?: string; initial_password?: string },
  ) => request<Member>(`/orgs/${orgId}/members`, json("POST", body)),
  updateMember: (orgId: string, memberId: string, role: Role) =>
    request<Member>(`/orgs/${orgId}/members/${memberId}`, json("PATCH", { role })),
  removeMember: (orgId: string, memberId: string) =>
    request<void>(`/orgs/${orgId}/members/${memberId}`, { method: "DELETE" }),
  audit: (orgId: string) => request<AuditEntry[]>(`/orgs/${orgId}/audit`),
};

// --- Projets (étape 2) -----------------------------------------------------

export type ProjectStatus = "draft" | "active" | "closed";
export type NodeLevel = "goal" | "outcome" | "output" | "activity" | "sub_activity";

export const CHILD_LEVEL: Record<NodeLevel, NodeLevel | null> = {
  goal: "outcome",
  outcome: "output",
  output: "activity",
  activity: "sub_activity",
  sub_activity: null,
};

export interface Project {
  id: string;
  code: string;
  title: string;
  description: string;
  donor: string;
  start_date: string | null;
  end_date: string | null;
  currency: string;
  language: string;
  status: ProjectStatus;
  zones: string[];
  target_groups: string[];
  exchange_rates: ExchangeRate[];
  created_at: string;
}

/** 1 unité de `currency` vaut `rate` unités de la devise du projet, à partir de `valid_from`. */
export interface ExchangeRate {
  currency: string;
  rate: string;
  valid_from: string;
}

export type ProjectInput = Pick<Project, "code" | "title"> &
  Partial<Omit<Project, "id" | "created_at" | "exchange_rates">>;

export interface ExpenseInput {
  amount: string;
  spent_on: string;
  reference: string;
  currency?: string;
  exchange_rate?: string | null;
}

export interface LogframeNode {
  id: string;
  parent_id: string | null;
  level: NodeLevel;
  code: string;
  title: string;
  description: string;
  assumptions: string;
  position: number;
  children: LogframeNode[];
}

export interface LogframeCheck {
  nodes_without_indicator: LogframeNode[];
  indicators_without_source: Indicator[];
  activities_without_budget: LogframeNode[];
}

export interface BudgetLine {
  id: string;
  activity_id: string | null;
  label: string;
  category: string;
  donor_line_code: string;
  quantity: string;
  unit: string;
  unit_cost: string;
  frequency: string;
  is_estimate: boolean;
  planned: string;
  spent: string;
}

export interface BudgetSummary {
  currency: string;
  planned: string;
  spent: string;
  execution_rate: number | null;
  over_budget_lines: number;
  by_activity: {
    activity_id: string | null;
    code: string;
    title: string;
    planned: string;
    spent: string;
    execution_rate: number | null;
  }[];
}

export interface Indicator {
  id: string;
  node_id: string;
  code: string;
  name: string;
  definition: string;
  unit: string;
  baseline: string | null;
  target: string | null;
  aggregation: "sum" | "latest";
  disaggregations: string[];
  source_of_verification: string;
  collection_method: string;
  frequency: string;
  owner_id: string | null;
  achieved: string | null;
  achievement_rate: number | null;
  period_targets: PeriodProgress[];
}

export interface PeriodTarget {
  period_start: string;
  period_end: string;
  target: string;
}

export interface PeriodProgress extends PeriodTarget {
  achieved: string | null;
  achievement_rate: number | null;
}

/** GET authentifié renvoyant le contenu brut (fichiers, images). */
export async function fetchBlob(path: string): Promise<Blob> {
  let response = await send(path, {}, tokenStore.get()?.access_token);
  if (response.status === 401 && tokenStore.get()) {
    const fresh = await refreshTokens();
    if (fresh) response = await send(path, {}, fresh.access_token);
  }
  if (!response.ok) throw new ApiError(response.status, await errorMessage(response));
  return response.blob();
}

export async function download(path: string, filename: string): Promise<void> {
  const url = URL.createObjectURL(await fetchBlob(path));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

const project = (orgId: string, projectId: string) => `/orgs/${orgId}/projects/${projectId}`;

export const projectsApi = {
  list: (orgId: string) => request<Project[]>(`/orgs/${orgId}/projects`),
  create: (orgId: string, body: ProjectInput) =>
    request<Project>(`/orgs/${orgId}/projects`, json("POST", body)),
  get: (orgId: string, projectId: string) => request<Project>(project(orgId, projectId)),
  update: (orgId: string, projectId: string, body: Partial<ProjectInput>) =>
    request<Project>(project(orgId, projectId), json("PATCH", body)),
  logframe: (orgId: string, projectId: string) =>
    request<LogframeNode[]>(`${project(orgId, projectId)}/logframe`),
  check: (orgId: string, projectId: string) =>
    request<LogframeCheck>(`${project(orgId, projectId)}/logframe/check`),
  addNode: (
    orgId: string,
    projectId: string,
    body: { level: NodeLevel; title: string; code?: string; parent_id?: string | null },
  ) => request<LogframeNode>(`${project(orgId, projectId)}/logframe/nodes`, json("POST", body)),
  deleteNode: (orgId: string, projectId: string, nodeId: string) =>
    request<void>(`${project(orgId, projectId)}/logframe/nodes/${nodeId}`, { method: "DELETE" }),
  budgetLines: (orgId: string, projectId: string) =>
    request<BudgetLine[]>(`${project(orgId, projectId)}/budget/lines`),
  budgetSummary: (orgId: string, projectId: string) =>
    request<BudgetSummary>(`${project(orgId, projectId)}/budget/summary`),
  addBudgetLine: (
    orgId: string,
    projectId: string,
    body: {
      label: string;
      activity_id: string | null;
      quantity: string;
      unit: string;
      unit_cost: string;
      frequency: string;
      donor_line_code: string;
    },
  ) => request<BudgetLine>(`${project(orgId, projectId)}/budget/lines`, json("POST", body)),
  deleteBudgetLine: (orgId: string, projectId: string, lineId: string) =>
    request<void>(`${project(orgId, projectId)}/budget/lines/${lineId}`, { method: "DELETE" }),
  setExchangeRates: (orgId: string, projectId: string, rates: ExchangeRate[]) =>
    request<Project>(`${project(orgId, projectId)}/exchange-rates`, json("PUT", rates)),
  documentPath: (orgId: string, projectId: string, format: "pdf" | "docx") =>
    `${project(orgId, projectId)}/export.${format}`,
  addExpense: (orgId: string, projectId: string, lineId: string, body: ExpenseInput) =>
    request<unknown>(
      `${project(orgId, projectId)}/budget/lines/${lineId}/expenses`,
      json("POST", body),
    ),
  indicators: (orgId: string, projectId: string) =>
    request<Indicator[]>(`${project(orgId, projectId)}/indicators`),
  updateIndicator: (
    orgId: string,
    projectId: string,
    indicatorId: string,
    body: { period_targets?: PeriodTarget[] },
  ) =>
    request<Indicator>(
      `${project(orgId, projectId)}/indicators/${indicatorId}`,
      json("PATCH", body),
    ),
  addIndicator: (
    orgId: string,
    projectId: string,
    body: {
      node_id: string;
      code: string;
      name: string;
      unit: string;
      baseline: string | null;
      target: string | null;
      aggregation: "sum" | "latest";
      source_of_verification: string;
    },
  ) => request<Indicator>(`${project(orgId, projectId)}/indicators`, json("POST", body)),
  deleteIndicator: (orgId: string, projectId: string, indicatorId: string) =>
    request<void>(`${project(orgId, projectId)}/indicators/${indicatorId}`, { method: "DELETE" }),
  addValue: (
    orgId: string,
    projectId: string,
    indicatorId: string,
    body: { period_start: string; period_end: string; value: string; source: string },
  ) =>
    request<unknown>(
      `${project(orgId, projectId)}/indicators/${indicatorId}/values`,
      json("POST", body),
    ),
  exportPath: (orgId: string, projectId: string) => `${project(orgId, projectId)}/export.xlsx`,
};

// --- Documents et IA (étape 3) -------------------------------------------------

export interface SourceDocument {
  id: string;
  filename: string;
  kind: string;
  size_bytes: number;
  status: "uploaded" | "ocr" | "extracted" | "failed";
  page_count: number;
  text_chars: number;
  error: string;
  created_at: string;
}

export interface SearchHit {
  document_id: string;
  filename: string;
  page: number;
  snippet: string;
  rank: number;
  // Trouvée par le sens, sans les mots de la recherche.
  semantic: boolean;
}

export interface Job {
  id: string;
  kind: string;
  status: "queued" | "running" | "succeeded" | "failed";
  result: Record<string, unknown>;
  error: string;
  created_at: string;
  finished_at: string | null;
}

interface Sourced {
  source_document: number | null;
  source_page: number | null;
  source_quote: string;
  verified: boolean;
}

export interface ProposedNode extends Sourced {
  ref: string;
  parent_ref: string | null;
  level: NodeLevel;
  code: string;
  title: string;
  assumptions: string;
}

export interface ProposedIndicator extends Sourced {
  node_ref: string;
  code: string;
  name: string;
  unit: string;
  baseline: number | null;
  target: number | null;
  aggregation: "sum" | "latest";
  disaggregations: string[];
  source_of_verification: string;
}

export interface ProposedBudgetLine extends Sourced {
  activity_ref: string | null;
  donor_line_code: string;
  label: string;
  category: string;
  quantity: number;
  unit: string;
  unit_cost: number;
  frequency: number;
  is_estimate: boolean;
}

export interface LogframeProposal {
  summary: string;
  currency: string | null;
  documents: string[];
  nodes: ProposedNode[];
  indicators: ProposedIndicator[];
  budget_lines: ProposedBudgetLine[];
  missing_information: string[];
}

export interface Proposal {
  id: string;
  kind: string;
  status: "pending" | "applied" | "rejected";
  payload: LogframeProposal;
  created_at: string;
  reviewed_at: string | null;
}

export interface ApplyLogframe {
  nodes: ProposedNode[];
  indicators: ProposedIndicator[];
  budget_lines: ProposedBudgetLine[];
}

export interface AiUsageRow {
  key: string;
  label: string;
  calls: number;
  errors: number;
  cost_usd: string;
  input_tokens: number;
  output_tokens: number;
}

export interface AiCallLog {
  id: string;
  created_at: string;
  purpose: string;
  model: string;
  status: string;
  error: string;
  cost_usd: string;
  duration_ms: number;
  input_tokens: number;
  output_tokens: number;
  project_code: string | null;
}

export interface AiUsage {
  month_cost_usd: string;
  monthly_budget_usd: string | null;
  calls_this_month: number;
  by_purpose: AiUsageRow[];
  by_project: AiUsageRow[];
  by_month: AiUsageRow[];
  recent: AiCallLog[];
}

export const aiApi = {
  usage: (orgId: string) => request<AiUsage>(`/orgs/${orgId}/ai/usage`),
  documents: (orgId: string, projectId: string) =>
    request<SourceDocument[]>(`${project(orgId, projectId)}/documents`),
  upload: (orgId: string, projectId: string, file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<SourceDocument>(`${project(orgId, projectId)}/documents`, {
      method: "POST",
      body,
    });
  },
  deleteDocument: (orgId: string, projectId: string, documentId: string) =>
    request<void>(`${project(orgId, projectId)}/documents/${documentId}`, { method: "DELETE" }),
  search: (orgId: string, projectId: string, q: string) =>
    request<SearchHit[]>(
      `${project(orgId, projectId)}/documents/search?q=${encodeURIComponent(q)}`,
    ),
  extract: (orgId: string, projectId: string) =>
    request<Job>(`${project(orgId, projectId)}/ai/logframe-extraction`, { method: "POST" }),
  job: (orgId: string, jobId: string) => request<Job>(`/orgs/${orgId}/jobs/${jobId}`),
  proposals: (orgId: string, projectId: string) =>
    request<Proposal[]>(`${project(orgId, projectId)}/proposals`),
  apply: (orgId: string, projectId: string, proposalId: string, body: ApplyLogframe) =>
    request<Proposal>(
      `${project(orgId, projectId)}/proposals/${proposalId}/apply`,
      json("POST", body),
    ),
  reject: (orgId: string, projectId: string, proposalId: string) =>
    request<Proposal>(`${project(orgId, projectId)}/proposals/${proposalId}/reject`, {
      method: "POST",
    }),
};

// --- Termes de référence (étape 4) --------------------------------------------

export type TorStatus = "draft" | "submitted" | "approved";

export interface TorSection {
  key: string;
  title: string;
  content: string;
}

export interface TorSummary {
  id: string;
  activity_id: string;
  title: string;
  status: TorStatus;
  version: number;
  updated_at: string;
}

export interface Tor extends TorSummary {
  project_id: string;
  sections: TorSection[];
  missing_information: string[];
  review_comment: string;
  submitted_at: string | null;
  approved_at: string | null;
  created_at: string;
}

export interface TorVersion {
  id: string;
  version: number;
  title: string;
  note: string;
  created_by: string | null;
  created_at: string;
}

export const torApi = {
  list: (orgId: string, projectId: string) =>
    request<TorSummary[]>(`${project(orgId, projectId)}/tors`),
  get: (orgId: string, projectId: string, torId: string) =>
    request<Tor>(`${project(orgId, projectId)}/tors/${torId}`),
  create: (orgId: string, projectId: string, activityId: string) =>
    request<Tor>(`${project(orgId, projectId)}/activities/${activityId}/tor`, { method: "POST" }),
  generate: (orgId: string, projectId: string, activityId: string, instructions: string) =>
    request<Job>(
      `${project(orgId, projectId)}/activities/${activityId}/tor/generate`,
      json("POST", { instructions }),
    ),
  update: (
    orgId: string,
    projectId: string,
    torId: string,
    body: { title: string; sections: TorSection[] },
  ) => request<Tor>(`${project(orgId, projectId)}/tors/${torId}`, json("PUT", body)),
  transition: (
    orgId: string,
    projectId: string,
    torId: string,
    action: "submit" | "approve" | "return" | "reopen",
    comment = "",
  ) =>
    request<Tor>(
      `${project(orgId, projectId)}/tors/${torId}/${action}`,
      action === "approve" || action === "return" ? json("POST", { comment }) : { method: "POST" },
    ),
  remove: (orgId: string, projectId: string, torId: string) =>
    request<void>(`${project(orgId, projectId)}/tors/${torId}`, { method: "DELETE" }),
  versions: (orgId: string, projectId: string, torId: string) =>
    request<TorVersion[]>(`${project(orgId, projectId)}/tors/${torId}/versions`),
  exportPath: (orgId: string, projectId: string, torId: string, format: "docx" | "pdf") =>
    `${project(orgId, projectId)}/tors/${torId}/export.${format}`,
};

// --- Exécution et collecte (étape 5) -------------------------------------------

export interface Participants {
  women: number;
  men: number;
  girls: number;
  boys: number;
  with_disability: number;
}

export type ExecutionStatus = "in_progress" | "completed";
export type EvidenceKind =
  "report" | "minutes" | "attendance" | "photo" | "audio" | "video" | "other";
export const EVIDENCE_KINDS: EvidenceKind[] = [
  "photo",
  "audio",
  "video",
  "report",
  "minutes",
  "attendance",
  "other",
];

export interface ExecutionInput {
  activity_id: string;
  title: string;
  start_date: string;
  end_date: string | null;
  location: string;
  latitude: number | null;
  longitude: number | null;
  participants: Participants;
  notes: string;
  status: ExecutionStatus;
  client_uuid: string;
}

export interface Execution extends Omit<ExecutionInput, "latitude" | "longitude" | "client_uuid"> {
  id: string;
  latitude: string | null;
  longitude: string | null;
  client_uuid: string | null;
  participants_total: number;
  evidence_count: number;
  spent: string;
  created_at: string;
}

export interface Evidence {
  id: string;
  execution_id: string;
  kind: EvidenceKind;
  filename: string;
  content_type: string;
  size_bytes: number;
  caption: string;
  taken_at: string | null;
  latitude: string | null;
  longitude: string | null;
  consent_given: boolean;
  has_thumbnail: boolean;
  page_count: number;
  faces: number;
  blur_faces: boolean;
  created_at: string;
}

export interface ExecutionExpense {
  id: string;
  budget_line_id: string;
  amount: string;
  spent_on: string;
  reference: string;
  description: string;
}

export interface ExecutionDetail extends Execution {
  evidence: Evidence[];
  expenses: ExecutionExpense[];
  planned: string;
}

export interface EvidenceInput {
  kind: EvidenceKind;
  caption: string;
  consent_given: boolean;
  client_uuid: string;
  // Lus sur le téléphone avant compression (la photo envoyée n'a plus d'EXIF).
  taken_at?: string;
  latitude?: number;
  longitude?: number;
}

export const executionsApi = {
  list: (orgId: string, projectId: string) =>
    request<Execution[]>(`${project(orgId, projectId)}/executions`),
  get: (orgId: string, projectId: string, executionId: string) =>
    request<ExecutionDetail>(`${project(orgId, projectId)}/executions/${executionId}`),
  create: (orgId: string, projectId: string, body: ExecutionInput) =>
    request<ExecutionDetail>(`${project(orgId, projectId)}/executions`, json("POST", body)),
  update: (
    orgId: string,
    projectId: string,
    executionId: string,
    body: Partial<Omit<ExecutionInput, "activity_id" | "client_uuid">>,
  ) =>
    request<ExecutionDetail>(
      `${project(orgId, projectId)}/executions/${executionId}`,
      json("PATCH", body),
    ),
  remove: (orgId: string, projectId: string, executionId: string) =>
    request<void>(`${project(orgId, projectId)}/executions/${executionId}`, {
      method: "DELETE",
    }),
  upload: (
    orgId: string,
    projectId: string,
    executionId: string,
    file: Blob,
    filename: string,
    meta: EvidenceInput,
  ) => {
    const body = new FormData();
    body.append("file", file, filename);
    body.append("kind", meta.kind);
    body.append("caption", meta.caption);
    body.append("consent_given", String(meta.consent_given));
    body.append("client_uuid", meta.client_uuid);
    if (meta.taken_at) body.append("taken_at", meta.taken_at);
    if (meta.latitude !== undefined && meta.longitude !== undefined) {
      body.append("latitude", String(meta.latitude));
      body.append("longitude", String(meta.longitude));
    }
    return request<Evidence>(`${project(orgId, projectId)}/executions/${executionId}/evidence`, {
      method: "POST",
      body,
    });
  },
  updateEvidence: (
    orgId: string,
    projectId: string,
    evidenceId: string,
    body: Partial<Pick<EvidenceInput, "kind" | "caption" | "consent_given">> & {
      blur_faces?: boolean;
    },
  ) =>
    request<Evidence>(`${project(orgId, projectId)}/evidence/${evidenceId}`, json("PATCH", body)),
  removeEvidence: (orgId: string, projectId: string, evidenceId: string) =>
    request<void>(`${project(orgId, projectId)}/evidence/${evidenceId}`, { method: "DELETE" }),
  evidencePath: (
    orgId: string,
    projectId: string,
    evidenceId: string,
    variant: "file" | "thumbnail",
  ) => `${project(orgId, projectId)}/evidence/${evidenceId}/${variant}`,
  addExpense: (
    orgId: string,
    projectId: string,
    executionId: string,
    body: ExpenseInput & { budget_line_id: string },
  ) =>
    request<ExecutionExpense>(
      `${project(orgId, projectId)}/executions/${executionId}/expenses`,
      json("POST", body),
    ),
};

// --- Rapports narratifs (étape 6) ----------------------------------------------

export interface ReportSummary {
  id: string;
  execution_id: string;
  title: string;
  status: TorStatus;
  version: number;
  updated_at: string;
}

export interface ReportSource {
  ref: string;
  label: string;
  evidence_id: string | null;
}

export interface IndicatorSuggestion {
  indicator_id: string;
  code: string;
  name: string;
  unit: string;
  value: string;
  justification: string;
  source_ref: string;
  applied_value_id: string | null;
}

export interface Report extends ReportSummary {
  project_id: string;
  sections: TorSection[];
  sources: ReportSource[];
  missing_information: string[];
  indicator_suggestions: IndicatorSuggestion[];
  review_comment: string;
  submitted_at: string | null;
  approved_at: string | null;
  created_at: string;
}

export const reportsApi = {
  list: (orgId: string, projectId: string, executionId?: string) =>
    request<ReportSummary[]>(
      `${project(orgId, projectId)}/reports${executionId ? `?execution_id=${executionId}` : ""}`,
    ),
  get: (orgId: string, projectId: string, reportId: string) =>
    request<Report>(`${project(orgId, projectId)}/reports/${reportId}`),
  generate: (orgId: string, projectId: string, executionId: string) =>
    request<Job>(`${project(orgId, projectId)}/executions/${executionId}/report/generate`, {
      method: "POST",
    }),
  update: (
    orgId: string,
    projectId: string,
    reportId: string,
    body: { title: string; sections: TorSection[] },
  ) => request<Report>(`${project(orgId, projectId)}/reports/${reportId}`, json("PUT", body)),
  transition: (
    orgId: string,
    projectId: string,
    reportId: string,
    action: "submit" | "approve" | "return" | "reopen",
    comment = "",
  ) =>
    request<Report>(
      `${project(orgId, projectId)}/reports/${reportId}/${action}`,
      action === "approve" || action === "return" ? json("POST", { comment }) : { method: "POST" },
    ),
  applySuggestion: (
    orgId: string,
    projectId: string,
    reportId: string,
    index: number,
    value: string,
  ) =>
    request<Report>(
      `${project(orgId, projectId)}/reports/${reportId}/suggestions/${index}/apply`,
      json("POST", { value }),
    ),
  remove: (orgId: string, projectId: string, reportId: string) =>
    request<void>(`${project(orgId, projectId)}/reports/${reportId}`, { method: "DELETE" }),
  versions: (orgId: string, projectId: string, reportId: string) =>
    request<TorVersion[]>(`${project(orgId, projectId)}/reports/${reportId}/versions`),
  exportPath: (orgId: string, projectId: string, reportId: string, format: "docx" | "pdf") =>
    `${project(orgId, projectId)}/reports/${reportId}/export.${format}`,
};

// --- Rapports périodiques (étape 7) ---------------------------------------------

export type PeriodicKind = "monthly" | "quarterly" | "annual" | "donor";
export const PERIODIC_KINDS: PeriodicKind[] = ["monthly", "quarterly", "annual", "donor"];

export interface PeriodicSummary {
  id: string;
  kind: PeriodicKind;
  period_start: string;
  period_end: string;
  title: string;
  status: TorStatus;
  version: number;
  updated_at: string;
}

export interface Periodic extends PeriodicSummary {
  project_id: string;
  sections: TorSection[];
  sources: ReportSource[];
  missing_information: string[];
  instructions: string;
  review_comment: string;
  submitted_at: string | null;
  approved_at: string | null;
  created_at: string;
}

const periodicPath = (orgId: string, projectId: string, reportId = "") =>
  `${project(orgId, projectId)}/periodic-reports${reportId ? `/${reportId}` : ""}`;

export const periodicApi = {
  list: (orgId: string, projectId: string) =>
    request<PeriodicSummary[]>(periodicPath(orgId, projectId)),
  get: (orgId: string, projectId: string, reportId: string) =>
    request<Periodic>(periodicPath(orgId, projectId, reportId)),
  create: (
    orgId: string,
    projectId: string,
    body: {
      kind: PeriodicKind;
      period_start: string;
      period_end: string;
      instructions: string;
      template_id?: string | null;
    },
  ) => request<Periodic>(periodicPath(orgId, projectId), json("POST", body)),
  generate: (orgId: string, projectId: string, reportId: string) =>
    request<Job>(`${periodicPath(orgId, projectId, reportId)}/generate`, { method: "POST" }),
  refresh: (orgId: string, projectId: string, reportId: string) =>
    request<Periodic>(`${periodicPath(orgId, projectId, reportId)}/refresh`, { method: "POST" }),
  update: (
    orgId: string,
    projectId: string,
    reportId: string,
    body: { title: string; sections: TorSection[] },
  ) => request<Periodic>(periodicPath(orgId, projectId, reportId), json("PUT", body)),
  transition: (
    orgId: string,
    projectId: string,
    reportId: string,
    action: "submit" | "approve" | "return" | "reopen",
    comment = "",
  ) =>
    request<Periodic>(
      `${periodicPath(orgId, projectId, reportId)}/${action}`,
      action === "approve" || action === "return" ? json("POST", { comment }) : { method: "POST" },
    ),
  remove: (orgId: string, projectId: string, reportId: string) =>
    request<void>(periodicPath(orgId, projectId, reportId), { method: "DELETE" }),
  versions: (orgId: string, projectId: string, reportId: string) =>
    request<TorVersion[]>(`${periodicPath(orgId, projectId, reportId)}/versions`),
  exportPath: (orgId: string, projectId: string, reportId: string, format: "docx" | "pdf") =>
    `${periodicPath(orgId, projectId, reportId)}/export.${format}`,
};

// --- Plaintes et retours, leçons apprises (étape 7) -----------------------------------

export type FeedbackChannel =
  "hotline" | "suggestion_box" | "community_meeting" | "field_visit" | "sms" | "email" | "other";
export const FEEDBACK_CHANNELS: FeedbackChannel[] = [
  "community_meeting",
  "field_visit",
  "hotline",
  "suggestion_box",
  "sms",
  "email",
  "other",
];
export type FeedbackCategory =
  | "information"
  | "suggestion"
  | "appreciation"
  | "complaint"
  | "fraud"
  | "sexual_exploitation"
  | "safety"
  | "other";
export const FEEDBACK_CATEGORIES: FeedbackCategory[] = [
  "complaint",
  "information",
  "suggestion",
  "appreciation",
  "fraud",
  "sexual_exploitation",
  "safety",
  "other",
];
export const SENSITIVE_CATEGORIES: FeedbackCategory[] = ["fraud", "sexual_exploitation", "safety"];
export type FeedbackStatus = "received" | "in_progress" | "responded" | "closed";
export const FEEDBACK_STATUSES: FeedbackStatus[] = [
  "received",
  "in_progress",
  "responded",
  "closed",
];

export interface FeedbackEntry {
  id: string;
  project_id: string;
  reference: string;
  received_on: string;
  channel: FeedbackChannel;
  category: FeedbackCategory;
  sensitive: boolean;
  description: string;
  location: string;
  activity_id: string | null;
  anonymous: boolean;
  contact: string;
  status: FeedbackStatus;
  assigned_to: string | null;
  response: string;
  responded_on: string | null;
  closed_on: string | null;
  created_by: string | null;
  created_at: string;
  due_on: string;
  overdue: boolean;
  response_days: number | null;
}

export interface FeedbackIn {
  received_on: string;
  channel: FeedbackChannel;
  category: FeedbackCategory;
  // Absent : déduit de la catégorie par l'API.
  sensitive?: boolean | null;
  description: string;
  location: string;
  activity_id: string | null;
  anonymous: boolean;
  contact: string;
  client_uuid: string;
}

export interface FeedbackSuggestion {
  category: FeedbackCategory;
  sensitive: boolean;
  urgency: "low" | "normal" | "high";
  summary: string;
  justification: string;
}

export interface FeedbackStats {
  total: number;
  open: number;
  overdue: number;
  response_rate: number | null;
  average_response_days: number | null;
  by_status: Partial<Record<FeedbackStatus, number>>;
  by_category: Partial<Record<FeedbackCategory, number>>;
  by_channel: Partial<Record<FeedbackChannel, number>>;
  hidden_sensitive: number;
}

export interface Lesson {
  id: string;
  project_id: string;
  project_code: string;
  title: string;
  description: string;
  recommendation: string;
  tags: string[];
  activity_id: string | null;
  source_report_id: string | null;
  created_by: string | null;
  created_at: string;
}

export type LessonIn = Pick<
  Lesson,
  "title" | "description" | "recommendation" | "tags" | "activity_id" | "source_report_id"
>;

export const accountabilityApi = {
  feedback: (orgId: string, projectId: string) =>
    request<FeedbackEntry[]>(`${project(orgId, projectId)}/feedback`),
  feedbackStats: (orgId: string, projectId: string) =>
    request<FeedbackStats>(`${project(orgId, projectId)}/feedback/stats`),
  classifyFeedback: (
    orgId: string,
    projectId: string,
    body: { description: string; channel: FeedbackChannel },
  ) =>
    request<FeedbackSuggestion>(
      `${project(orgId, projectId)}/feedback/classify`,
      json("POST", body),
    ),
  addFeedback: (orgId: string, projectId: string, body: FeedbackIn) =>
    request<FeedbackEntry>(`${project(orgId, projectId)}/feedback`, json("POST", body)),
  updateFeedback: (
    orgId: string,
    projectId: string,
    feedbackId: string,
    body: Partial<
      Pick<
        FeedbackEntry,
        "status" | "assigned_to" | "response" | "responded_on" | "category" | "sensitive"
      >
    >,
  ) =>
    request<FeedbackEntry>(
      `${project(orgId, projectId)}/feedback/${feedbackId}`,
      json("PATCH", body),
    ),
  deleteFeedback: (orgId: string, projectId: string, feedbackId: string) =>
    request<void>(`${project(orgId, projectId)}/feedback/${feedbackId}`, { method: "DELETE" }),
  lessons: (orgId: string, projectId: string | null, q = "", tag = "") => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (tag) params.set("tag", tag);
    const base = projectId ? `${project(orgId, projectId)}/lessons` : `/orgs/${orgId}/lessons`;
    return request<Lesson[]>(`${base}${params.size ? `?${params}` : ""}`);
  },
  addLesson: (orgId: string, projectId: string, body: LessonIn) =>
    request<Lesson>(`${project(orgId, projectId)}/lessons`, json("POST", body)),
  updateLesson: (orgId: string, projectId: string, lessonId: string, body: Partial<LessonIn>) =>
    request<Lesson>(`${project(orgId, projectId)}/lessons/${lessonId}`, json("PATCH", body)),
  deleteLesson: (orgId: string, projectId: string, lessonId: string) =>
    request<void>(`${project(orgId, projectId)}/lessons/${lessonId}`, { method: "DELETE" }),
};

// --- Modèles de documents ---------------------------------------------------------------

export const TEMPLATE_KINDS = ["tor", "report", "periodic"] as const;
export type TemplateKind = (typeof TEMPLATE_KINDS)[number];

export interface TemplateSection {
  key: string;
  title: string;
  guidance: string;
}

export interface TemplateLayout {
  header: string;
  footer: string;
  color: string;
}

export interface DocumentTemplate {
  id: string;
  kind: TemplateKind;
  name: string;
  donor: string;
  is_default: boolean;
  sections: TemplateSection[];
  layout: TemplateLayout;
  created_at: string;
}

export type TemplateIn = Omit<DocumentTemplate, "id" | "created_at">;

export interface BuiltinSection {
  key: string;
  title: string;
  computed: boolean;
}

export type BuiltinTemplates = Record<TemplateKind, BuiltinSection[]>;

export const templatesApi = {
  list: (orgId: string) => request<DocumentTemplate[]>(`/orgs/${orgId}/templates`),
  builtin: (orgId: string) => request<BuiltinTemplates>(`/orgs/${orgId}/templates/builtin`),
  create: (orgId: string, body: TemplateIn) =>
    request<DocumentTemplate>(`/orgs/${orgId}/templates`, json("POST", body)),
  update: (orgId: string, id: string, body: Partial<TemplateIn>) =>
    request<DocumentTemplate>(`/orgs/${orgId}/templates/${id}`, json("PATCH", body)),
  remove: (orgId: string, id: string) =>
    request<void>(`/orgs/${orgId}/templates/${id}`, { method: "DELETE" }),
};

// --- Formulaires de collecte -------------------------------------------------------------

export const FIELD_TYPES = [
  "text",
  "number",
  "integer",
  "select",
  "multiselect",
  "yesno",
  "date",
] as const;
export type FieldType = (typeof FIELD_TYPES)[number];
export type FormStatus = "draft" | "published" | "closed";
export type AnswerValue = string | number | boolean | string[];

export interface FormField {
  key: string;
  label: string;
  type: FieldType;
  required: boolean;
  options: string[];
  hint: string;
}

export interface CollectionForm {
  id: string;
  project_id: string;
  title: string;
  description: string;
  status: FormStatus;
  fields: FormField[];
  activity_id: string | null;
  created_at: string;
  submissions: number;
}

export type FormInput = Pick<CollectionForm, "title" | "description" | "activity_id" | "fields">;

export interface SubmissionInput {
  answers: Record<string, AnswerValue>;
  location: string;
  latitude: number | null;
  longitude: number | null;
  collected_at: string;
  client_uuid: string;
}

export interface Submission extends Omit<SubmissionInput, "client_uuid"> {
  id: string;
  form_id: string;
  submitted_by: string | null;
  submitter_name: string;
}

export interface FieldSummary {
  key: string;
  label: string;
  type: FieldType;
  answered: number;
  counts: Record<string, number>;
  total: number | null;
  mean: number | null;
  min: number | null;
  max: number | null;
  samples: string[];
}

export interface FormSummary {
  submissions: number;
  fields: FieldSummary[];
}

const formsPath = (orgId: string, projectId: string, formId?: string) =>
  `${project(orgId, projectId)}/forms${formId ? `/${formId}` : ""}`;

export const formsApi = {
  list: (orgId: string, projectId: string) =>
    request<CollectionForm[]>(formsPath(orgId, projectId)),
  get: (orgId: string, projectId: string, formId: string) =>
    request<CollectionForm>(formsPath(orgId, projectId, formId)),
  create: (orgId: string, projectId: string, body: FormInput) =>
    request<CollectionForm>(formsPath(orgId, projectId), json("POST", body)),
  update: (
    orgId: string,
    projectId: string,
    formId: string,
    body: Partial<FormInput> & { status?: FormStatus },
  ) => request<CollectionForm>(formsPath(orgId, projectId, formId), json("PATCH", body)),
  remove: (orgId: string, projectId: string, formId: string) =>
    request<void>(formsPath(orgId, projectId, formId), { method: "DELETE" }),
  submit: (orgId: string, projectId: string, formId: string, body: SubmissionInput) =>
    request<Submission>(`${formsPath(orgId, projectId, formId)}/submissions`, json("POST", body)),
  submissions: (orgId: string, projectId: string, formId: string) =>
    request<Submission[]>(`${formsPath(orgId, projectId, formId)}/submissions`),
  removeSubmission: (orgId: string, projectId: string, formId: string, id: string) =>
    request<void>(`${formsPath(orgId, projectId, formId)}/submissions/${id}`, {
      method: "DELETE",
    }),
  summary: (orgId: string, projectId: string, formId: string) =>
    request<FormSummary>(`${formsPath(orgId, projectId, formId)}/summary`),
  exportPath: (orgId: string, projectId: string, formId: string) =>
    `${formsPath(orgId, projectId, formId)}/export.xlsx`,
};
