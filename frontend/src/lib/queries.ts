import { queryOptions } from "@tanstack/react-query";

import { api } from "./api";

export const meQuery = queryOptions({ queryKey: ["me"], queryFn: api.me });

export const membersQuery = (orgId: string) =>
  queryOptions({ queryKey: ["orgs", orgId, "members"], queryFn: () => api.members(orgId) });

export const auditQuery = (orgId: string) =>
  queryOptions({ queryKey: ["orgs", orgId, "audit"], queryFn: () => api.audit(orgId) });
