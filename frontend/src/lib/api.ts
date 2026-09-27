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
  created_at: string;
}

export type ProjectInput = Pick<Project, "code" | "title"> &
  Partial<Omit<Project, "id" | "created_at">>;

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
  addExpense: (
    orgId: string,
    projectId: string,
    lineId: string,
    body: { amount: string; spent_on: string; reference: string },
  ) =>
    request<unknown>(
      `${project(orgId, projectId)}/budget/lines/${lineId}/expenses`,
      json("POST", body),
    ),
  indicators: (orgId: string, projectId: string) =>
    request<Indicator[]>(`${project(orgId, projectId)}/indicators`),
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
  status: "uploaded" | "extracted" | "failed";
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

export const aiApi = {
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
export type EvidenceKind = "report" | "minutes" | "attendance" | "photo" | "other";
export const EVIDENCE_KINDS: EvidenceKind[] = ["photo", "report", "minutes", "attendance", "other"];

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
    return request<Evidence>(`${project(orgId, projectId)}/executions/${executionId}/evidence`, {
      method: "POST",
      body,
    });
  },
  updateEvidence: (
    orgId: string,
    projectId: string,
    evidenceId: string,
    body: Partial<Omit<EvidenceInput, "client_uuid">>,
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
    body: { budget_line_id: string; amount: string; spent_on: string; reference: string },
  ) =>
    request<ExecutionExpense>(
      `${project(orgId, projectId)}/executions/${executionId}/expenses`,
      json("POST", body),
    ),
};
