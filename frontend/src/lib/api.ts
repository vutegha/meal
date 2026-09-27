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
  if (init.body) headers.set("Content-Type", "application/json");
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

export async function download(path: string, filename: string): Promise<void> {
  let response = await send(path, {}, tokenStore.get()?.access_token);
  if (response.status === 401 && tokenStore.get()) {
    const fresh = await refreshTokens();
    if (fresh) response = await send(path, {}, fresh.access_token);
  }
  if (!response.ok) throw new ApiError(response.status, await errorMessage(response));
  const url = URL.createObjectURL(await response.blob());
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
