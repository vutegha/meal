import type { QueryClient } from "@tanstack/react-query";
import {
  createRootRouteWithContext,
  createRoute,
  createRouter,
  Outlet,
  redirect,
  type RouterHistory,
} from "@tanstack/react-router";

import { AccountPage } from "@/features/account/AccountPage";
import { AdminPage } from "@/features/admin/AdminPage";
import { ForgotPasswordPage } from "@/features/auth/ForgotPasswordPage";
import { LoginPage } from "@/features/auth/LoginPage";
import { RegisterPage } from "@/features/auth/RegisterPage";
import { ResetPasswordPage } from "@/features/auth/ResetPasswordPage";
import { BillingPage } from "@/features/orgs/BillingPage";
import { FeatureGate } from "@/features/orgs/FeatureGate";
import { MembersPage } from "@/features/orgs/MembersPage";
import { OrgDashboardPage } from "@/features/orgs/OrgDashboardPage";
import { OrgLessonsPage } from "@/features/orgs/OrgLessonsPage";
import { PrivacyPage } from "@/features/orgs/PrivacyPage";
import { TemplatesPage } from "@/features/orgs/TemplatesPage";
import { OrgLayout } from "@/features/orgs/OrgLayout";
import { ProjectPage } from "@/features/projects/ProjectPage";
import { ProjectsPage } from "@/features/projects/ProjectsPage";
import { PROJECT_TABS, type ProjectTab } from "@/features/projects/tabs";
import { FeaturesPage } from "@/features/site/FeaturesPage";
import { HomePage } from "@/features/site/HomePage";
import { PricingPage } from "@/features/site/PricingPage";
import type { AccountType } from "@/lib/api";
import { type Cycle, CYCLES } from "@/lib/billing";
import { loadProfile } from "@/lib/session";
import { tokenStore } from "@/lib/tokens";

interface RouterContext {
  queryClient: QueryClient;
}

const rootRoute = createRootRouteWithContext<RouterContext>()({ component: Outlet });

const requireAuth = () => {
  if (!tokenStore.get()) throw redirect({ to: "/login" });
};

async function loadMe(queryClient: QueryClient) {
  // Hors ligne, le profil gardé sur l'appareil suffit : l'agent garde accès à sa saisie.
  const me = await loadProfile(queryClient).catch(() => null);
  if (!me) throw redirect({ to: "/login" });
  return me;
}

// Accueil du site public ; une personne connectée va directement à son espace.
const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  beforeLoad: async ({ context }) => {
    if (!tokenStore.get()) return;
    const me = await loadMe(context.queryClient);
    const first = me.organizations[0];
    if (first) throw redirect({ to: "/orgs/$orgId", params: { orgId: first.id } });
  },
  component: HomePage,
});

const featuresRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/fonctionnalites",
  component: FeaturesPage,
});

const pricingRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tarifs",
  component: PricingPage,
});

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  component: LoginPage,
});

const forgotPasswordRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/forgot-password",
  component: ForgotPasswordPage,
});

const resetPasswordRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/reset-password",
  validateSearch: (search: Record<string, unknown>): { token?: string } => ({
    token: typeof search.token === "string" ? search.token : undefined,
  }),
  component: ResetPasswordPage,
});

const registerRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/register",
  // Formule choisie sur la page Tarifs.
  validateSearch: (
    search: Record<string, unknown>,
  ): { type?: AccountType; plan?: string; cycle?: Cycle } => ({
    type: search.type === "individual" || search.type === "organization" ? search.type : undefined,
    plan: typeof search.plan === "string" ? search.plan : undefined,
    cycle: CYCLES.includes(search.cycle as Cycle) ? (search.cycle as Cycle) : undefined,
  }),
  component: RegisterPage,
});

// Administration de la plateforme ; l'API répond 404 aux autres comptes.
const adminRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/admin",
  beforeLoad: async ({ context }) => {
    requireAuth();
    const me = await loadMe(context.queryClient);
    if (!me.is_platform_admin) throw redirect({ to: "/" });
  },
  component: AdminPage,
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

const orgDashboardRoute = createRoute({
  getParentRoute: () => orgRoute,
  path: "/dashboard",
  component: OrgDashboardPage,
});

const membersRoute = createRoute({
  getParentRoute: () => orgRoute,
  path: "/members",
  component: () => (
    <FeatureGate feature="team">
      <MembersPage />
    </FeatureGate>
  ),
});

const lessonsRoute = createRoute({
  getParentRoute: () => orgRoute,
  path: "/lessons",
  component: () => (
    <FeatureGate feature="org_lessons">
      <OrgLessonsPage />
    </FeatureGate>
  ),
});

const templatesRoute = createRoute({
  getParentRoute: () => orgRoute,
  path: "/templates",
  component: () => (
    <FeatureGate feature="templates">
      <TemplatesPage />
    </FeatureGate>
  ),
});

const privacyRoute = createRoute({
  getParentRoute: () => orgRoute,
  path: "/privacy",
  component: PrivacyPage,
});

const accountRoute = createRoute({
  getParentRoute: () => orgRoute,
  path: "/account",
  component: AccountPage,
});

const billingRoute = createRoute({
  getParentRoute: () => orgRoute,
  path: "/billing",
  component: BillingPage,
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
    periodic?: string;
    form?: string;
    setup?: boolean;
  } => ({
    tab: PROJECT_TABS.includes(search.tab as ProjectTab) ? (search.tab as ProjectTab) : "dashboard",
    tor: typeof search.tor === "string" ? search.tor : undefined,
    execution: typeof search.execution === "string" ? search.execution : undefined,
    periodic: typeof search.periodic === "string" ? search.periodic : undefined,
    form: typeof search.form === "string" ? search.form : undefined,
    // Projet tout juste créé avec ses documents : l'extraction démarre d'elle-même.
    setup: search.setup === true ? true : undefined,
  }),
  component: ProjectPage,
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  featuresRoute,
  pricingRoute,
  loginRoute,
  forgotPasswordRoute,
  resetPasswordRoute,
  registerRoute,
  adminRoute,
  orgRoute.addChildren([
    orgIndexRoute,
    orgDashboardRoute,
    lessonsRoute,
    templatesRoute,
    membersRoute,
    billingRoute,
    accountRoute,
    privacyRoute,
    projectRoute,
  ]),
]);

export function createAppRouter(queryClient: QueryClient, history?: RouterHistory) {
  return createRouter({ routeTree, history, context: { queryClient }, defaultPreload: "intent" });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof createAppRouter>;
  }
}
