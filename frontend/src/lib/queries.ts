import { queryOptions } from "@tanstack/react-query";

import { aiApi, api, projectsApi } from "./api";

export const meQuery = queryOptions({ queryKey: ["me"], queryFn: api.me });

export const membersQuery = (orgId: string) =>
  queryOptions({ queryKey: ["orgs", orgId, "members"], queryFn: () => api.members(orgId) });

export const auditQuery = (orgId: string) =>
  queryOptions({ queryKey: ["orgs", orgId, "audit"], queryFn: () => api.audit(orgId) });

export const projectsQuery = (orgId: string) =>
  queryOptions({ queryKey: ["orgs", orgId, "projects"], queryFn: () => projectsApi.list(orgId) });

const projectKey = (orgId: string, projectId: string) => ["orgs", orgId, "projects", projectId];

export const projectQuery = (orgId: string, projectId: string) =>
  queryOptions({
    queryKey: projectKey(orgId, projectId),
    queryFn: () => projectsApi.get(orgId, projectId),
  });

export const logframeQuery = (orgId: string, projectId: string) =>
  queryOptions({
    queryKey: [...projectKey(orgId, projectId), "logframe"],
    queryFn: () => projectsApi.logframe(orgId, projectId),
  });

export const checkQuery = (orgId: string, projectId: string) =>
  queryOptions({
    queryKey: [...projectKey(orgId, projectId), "check"],
    queryFn: () => projectsApi.check(orgId, projectId),
  });

export const budgetLinesQuery = (orgId: string, projectId: string) =>
  queryOptions({
    queryKey: [...projectKey(orgId, projectId), "budget-lines"],
    queryFn: () => projectsApi.budgetLines(orgId, projectId),
  });

export const budgetSummaryQuery = (orgId: string, projectId: string) =>
  queryOptions({
    queryKey: [...projectKey(orgId, projectId), "budget-summary"],
    queryFn: () => projectsApi.budgetSummary(orgId, projectId),
  });

export const indicatorsQuery = (orgId: string, projectId: string) =>
  queryOptions({
    queryKey: [...projectKey(orgId, projectId), "indicators"],
    queryFn: () => projectsApi.indicators(orgId, projectId),
  });

export const documentsQuery = (orgId: string, projectId: string) =>
  queryOptions({
    queryKey: [...projectKey(orgId, projectId), "documents"],
    queryFn: () => aiApi.documents(orgId, projectId),
  });

export const proposalsQuery = (orgId: string, projectId: string) =>
  queryOptions({
    queryKey: [...projectKey(orgId, projectId), "proposals"],
    queryFn: () => aiApi.proposals(orgId, projectId),
  });
