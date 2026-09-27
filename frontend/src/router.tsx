import type { QueryClient } from "@tanstack/react-query";
import {
  createRootRouteWithContext,
  createRoute,
  createRouter,
  Outlet,
  redirect,
  type RouterHistory,
} from "@tanstack/react-router";

import { LoginPage } from "@/features/auth/LoginPage";
import { RegisterPage } from "@/features/auth/RegisterPage";
import { MembersPage } from "@/features/orgs/MembersPage";
import { OrgLayout } from "@/features/orgs/OrgLayout";
import { ProjectPage } from "@/features/projects/ProjectPage";
import { ProjectsPage } from "@/features/projects/ProjectsPage";
import { PROJECT_TABS, type ProjectTab } from "@/features/projects/tabs";
import { meQuery } from "@/lib/queries";
import { tokenStore } from "@/lib/tokens";

interface RouterContext {
  queryClient: QueryClient;
}

const rootRoute = createRootRouteWithContext<RouterContext>()({ component: Outlet });

const requireAuth = () => {
  if (!tokenStore.get()) throw redirect({ to: "/login" });
};

async function loadMe(queryClient: QueryClient) {
  try {
    return await queryClient.ensureQueryData(meQuery);
  } catch {
    tokenStore.set(null);
    throw redirect({ to: "/login" });
  }
}

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  beforeLoad: async ({ context }) => {
    requireAuth();
    const me = await loadMe(context.queryClient);
    const first = me.organizations[0];
    if (first) throw redirect({ to: "/orgs/$orgId", params: { orgId: first.id } });
  },
  component: () => null,
});

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  component: LoginPage,
});

const registerRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/register",
  component: RegisterPage,
});

const orgRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/orgs/$orgId",
  beforeLoad: async ({ context }) => {
    requireAuth();
    await loadMe(context.queryClient);
  },
  component: OrgLayout,
});

const orgIndexRoute = createRoute({
  getParentRoute: () => orgRoute,
  path: "/",
  component: ProjectsPage,
});

const membersRoute = createRoute({
  getParentRoute: () => orgRoute,
  path: "/members",
  component: MembersPage,
});

const projectRoute = createRoute({
  getParentRoute: () => orgRoute,
  path: "/projects/$projectId",
  validateSearch: (
    search: Record<string, unknown>,
  ): {
    tab: ProjectTab;
    tor?: string;
    execution?: string;
  } => ({
    tab: PROJECT_TABS.includes(search.tab as ProjectTab) ? (search.tab as ProjectTab) : "dashboard",
    tor: typeof search.tor === "string" ? search.tor : undefined,
    execution: typeof search.execution === "string" ? search.execution : undefined,
  }),
  component: ProjectPage,
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  loginRoute,
  registerRoute,
  orgRoute.addChildren([orgIndexRoute, membersRoute, projectRoute]),
]);

export function createAppRouter(queryClient: QueryClient, history?: RouterHistory) {
  return createRouter({ routeTree, history, context: { queryClient }, defaultPreload: "intent" });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof createAppRouter>;
  }
}
