import { queryOptions } from "@tanstack/react-query";

import {
  accountabilityApi,
  aiApi,
  api,
  executionsApi,
  periodicApi,
  projectsApi,
  reportsApi,
  torApi,
} from "./api";

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

export const torsQuery = (orgId: string, projectId: string) =>
  queryOptions({
    queryKey: [...projectKey(orgId, projectId), "tors"],
    queryFn: () => torApi.list(orgId, projectId),
  });

export const torQuery = (orgId: string, projectId: string, torId: string) =>
  queryOptions({
    queryKey: [...projectKey(orgId, projectId), "tors", torId],
    queryFn: () => torApi.get(orgId, projectId, torId),
  });

export const torVersionsQuery = (orgId: string, projectId: string, torId: string) =>
  queryOptions({
    queryKey: [...projectKey(orgId, projectId), "tors", torId, "versions"],
    queryFn: () => torApi.versions(orgId, projectId, torId),
  });

export const executionsQuery = (orgId: string, projectId: string) =>
  queryOptions({
    queryKey: [...projectKey(orgId, projectId), "executions"],
    queryFn: () => executionsApi.list(orgId, projectId),
  });

export const executionQuery = (orgId: string, projectId: string, executionId: string) =>
  queryOptions({
    queryKey: [...projectKey(orgId, projectId), "executions", executionId],
    queryFn: () => executionsApi.get(orgId, projectId, executionId),
  });

export const executionReportsQuery = (orgId: string, projectId: string, executionId: string) =>
  queryOptions({
    queryKey: [...projectKey(orgId, projectId), "reports", { executionId }],
    queryFn: () => reportsApi.list(orgId, projectId, executionId),
  });

export const reportQuery = (orgId: string, projectId: string, reportId: string) =>
  queryOptions({
    queryKey: [...projectKey(orgId, projectId), "reports", reportId],
    queryFn: () => reportsApi.get(orgId, projectId, reportId),
  });

export const reportsQuery = (orgId: string, projectId: string) =>
  queryOptions({
    queryKey: [...projectKey(orgId, projectId), "reports"],
    queryFn: () => reportsApi.list(orgId, projectId),
  });

export const periodicListQuery = (orgId: string, projectId: string) =>
  queryOptions({
    queryKey: [...projectKey(orgId, projectId), "periodic"],
    queryFn: () => periodicApi.list(orgId, projectId),
  });

export const periodicQuery = (orgId: string, projectId: string, reportId: string) =>
  queryOptions({
    queryKey: [...projectKey(orgId, projectId), "periodic", reportId],
    queryFn: () => periodicApi.get(orgId, projectId, reportId),
  });

export const feedbackQuery = (orgId: string, projectId: string) =>
  queryOptions({
    queryKey: [...projectKey(orgId, projectId), "feedback"],
    queryFn: () => accountabilityApi.feedback(orgId, projectId),
  });

export const feedbackStatsQuery = (orgId: string, projectId: string) =>
  queryOptions({
    queryKey: [...projectKey(orgId, projectId), "feedback", "stats"],
    queryFn: () => accountabilityApi.feedbackStats(orgId, projectId),
  });

export const lessonsQuery = (orgId: string, projectId: string | null, q = "", tag = "") =>
  queryOptions({
    queryKey: projectId
      ? [...projectKey(orgId, projectId), "lessons", { q, tag }]
      : ["orgs", orgId, "lessons", { q, tag }],
    queryFn: () => accountabilityApi.lessons(orgId, projectId, q, tag),
  });
