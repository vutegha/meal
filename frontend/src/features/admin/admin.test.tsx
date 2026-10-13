import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { tokenStore } from "@/lib/tokens";
import { createAppRouter } from "@/router";

const org = {
  id: "org-1",
  name: "Opérations",
  slug: "ops",
  default_language: "fr",
  created_at: "2026-09-27T10:00:00Z",
  role: "admin",
  account_type: "organization",
  plan: "team",
  features: ["projects"],
};
const me = (admin: boolean) => ({
  id: "u1",
  email: "ops@wemeal.org",
  full_name: "Ops",
  is_active: true,
  is_platform_admin: admin,
  organizations: [org],
});
const row = {
  organization_id: "org-2",
  organization_name: "ONG Kivu",
  organization_created_at: "2026-10-01T10:00:00Z",
  contact_email: "awa@kivu.org",
  contact_name: "Awa",
  plan: "team",
  account_type: "organization",
  cycle: "monthly",
  status: "expired",
  trial_ends_at: "2026-10-05T10:00:00Z",
  current_period_end: null,
  cancel_at_period_end: false,
  credits: 0,
  members: 4,
  projects: 2,
  credits_used_this_month: 12,
  last_payment_at: null,
  total_paid: "0.00",
};
const list = {
  summary: {
    organizations: 1,
    by_status: { trialing: 0, active: 0, canceled: 0, expired: 1 },
    by_plan: { solo: 0, team: 1, institution: 0 },
    monthly_recurring: "0.00",
    revenue_last_30_days: "0.00",
    currency: "USD",
  },
  items: [row],
};
const catalog = {
  currency: "USD",
  trial_days: 14,
  welcome_credits: 5,
  credit_packs: [10],
  plans: ["solo", "team", "institution"].map((id) => ({
    id,
    account_type: id === "solo" ? "individual" : "organization",
    prices: { monthly: "1", annual: "10", credit: "1" },
    limits: { projects: null, members: null, monthly_credits: 20 },
    features: [],
  })),
};

let patched: { url: string; body: Record<string, unknown> } | null = null;

function setup(admin: boolean) {
  tokenStore.set({ access_token: "a", refresh_token: "r" });
  patched = null;
  const fetch = vi.fn(async (input: string | Request) => {
    const url = typeof input === "string" ? input : input.url;
    let body: unknown = [];
    if (url.endsWith("/auth/me")) body = me(admin);
    else if (url.endsWith("/billing/plans")) body = catalog;
    else if (typeof input !== "string" && input.method === "PATCH") {
      const changes = (await input.json()) as Record<string, unknown>;
      patched = { url, body: changes };
      body = { ...row, ...changes, status: "active" };
    } else if (url.includes("/admin/subscriptions")) body = list;
    return new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetch);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createAppRouter(queryClient, createMemoryHistory({ initialEntries: ["/admin"] }));
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { router };
}

afterEach(() => {
  vi.unstubAllGlobals();
  tokenStore.set(null);
});

it("liste les abonnements et modifie celui d'un espace", async () => {
  setup(true);
  expect(
    await screen.findByRole("heading", { name: "Abonnements de la plateforme" }),
  ).toBeInTheDocument();
  const line = (await screen.findByText("ONG Kivu")).closest("tr")!;
  expect(within(line).getByText("Expirée")).toBeInTheDocument();

  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Gérer l'abonnement de ONG Kivu" }));
  // Les filtres viennent en premier, puis le formulaire de l'espace choisi.
  await user.selectOptions(screen.getAllByLabelText("Formule")[1], "institution");
  await user.selectOptions(screen.getAllByLabelText("Statut")[1], "active");
  await user.type(screen.getByLabelText("Motif"), "Virement reçu");
  await user.click(screen.getByRole("button", { name: "Enregistrer" }));

  expect(await screen.findByText("Abonnement mis à jour.")).toBeInTheDocument();
  expect(patched?.url).toContain("/api/v1/admin/subscriptions/org-2");
  expect(patched?.body).toEqual({ plan: "institution", status: "active", note: "Virement reçu" });
});

it("renvoie les autres comptes vers l'accueil", async () => {
  const { router } = setup(false);
  await waitFor(() => expect(router.state.location.pathname).toBe("/orgs/org-1"));
});
