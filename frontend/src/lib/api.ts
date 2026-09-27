import { type Tokens, tokenStore } from "./tokens";

export type Role =
  | "admin"
  | "project_manager"
  | "meal_officer"
  | "field_agent"
  | "finance"
  | "viewer";

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
