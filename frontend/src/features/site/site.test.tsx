import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { tokenStore } from "@/lib/tokens";
import { createAppRouter } from "@/router";

const core = ["projects", "ai_extraction", "tor", "offline_collection", "reports"];
const team = ["team", "templates", "org_lessons", "audit"];
const plan = (id: string, type: string, monthly: string, annual: string, features: string[]) => ({
  id,
  account_type: type,
  prices: { monthly, annual, credit: "1.50" },
  limits: { projects: 3, members: type === "individual" ? 1 : 15, monthly_credits: 20 },
  features,
});
const catalog = {
  currency: "USD",
  trial_days: 14,
  welcome_credits: 5,
  credit_packs: [10, 50, 200],
  plans: [
    plan("solo", "individual", "12", "120", core),
    plan("team", "organization", "59", "590", [...core, ...team]),
    plan("institution", "organization", "249", "2490", [...core, ...team, "messaging"]),
  ],
};
const me = {
  id: "u1",
  email: "awa@example.org",
  full_name: "Awa Diallo",
  is_active: true,
  is_platform_admin: false,
  organizations: [
    {
      id: "org-1",
      name: "Espace de Awa Diallo",
      slug: "espace",
      default_language: "fr",
      created_at: "2026-09-27T10:00:00Z",
      role: "admin",
      account_type: "individual",
      plan: "solo",
      features: core,
    },
  ],
};

function setup(path: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: string | Request) => {
      const url = typeof input === "string" ? input : input.url;
      const body = url.endsWith("/billing/plans") ? catalog : url.endsWith("/auth/me") ? me : [];
      return Promise.resolve(
        new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } }),
      );
    }),
  );
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createAppRouter(queryClient, createMemoryHistory({ initialEntries: [path] }));
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

afterEach(() => {
  vi.unstubAllGlobals();
  tokenStore.set(null);
});

it("présente l'application aux visiteurs sur la page d'accueil", async () => {
  setup("/");
  expect(
    await screen.findByRole("heading", { name: /Du document de projet au rapport final/ }),
  ).toBeInTheDocument();
  expect(screen.getAllByRole("link", { name: "Tarifs" })[0]).toHaveAttribute("href", "/tarifs");
});

it("affiche les formules selon le cycle et mène à l'inscription", async () => {
  const router = setup("/tarifs");
  const solo = await screen.findByRole("article", { name: "Solo" });
  expect(within(solo).getByText("Compte individuel")).toBeInTheDocument();
  expect(within(solo).getByText("/ mois")).toBeInTheDocument();

  const user = userEvent.setup();
  await user.click(screen.getByRole("radio", { name: /Annuel/ }));
  const team2 = screen.getByRole("article", { name: "Équipe" });
  expect(within(team2).getByText("/ an")).toBeInTheDocument();
  expect(within(team2).getByText(/Tout Solo, plus/)).toBeInTheDocument();
  expect(within(team2).getByText("Membres et rôles")).toBeInTheDocument();

  await user.click(within(team2).getByRole("link", { name: "Choisir Équipe" }));
  expect(router.state.location.pathname).toBe("/register");
  expect(router.state.location.search).toEqual({
    type: "organization",
    plan: "team",
    cycle: "annual",
  });
  expect(await screen.findByLabelText("Nom de votre organisation")).toBeInTheDocument();
});

it("ne demande pas de nom d'organisation pour un compte individuel", async () => {
  setup("/register?type=individual");
  expect(await screen.findByLabelText("Nom complet")).toBeInTheDocument();
  expect(screen.queryByLabelText("Nom de votre organisation")).not.toBeInTheDocument();
  expect(screen.getByRole("radio", { name: /Individuel/ })).toBeChecked();
});

it("réserve les membres aux formules qui les ouvrent", async () => {
  tokenStore.set({ access_token: "a", refresh_token: "r" });
  setup("/orgs/org-1/members");
  expect(await screen.findByRole("heading", { name: "Membres et rôles" })).toBeInTheDocument();
  expect(await screen.findByText("Formule Équipe")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Voir les formules" })).toHaveAttribute(
    "href",
    "/orgs/org-1/billing",
  );
  const nav = screen.getByRole("navigation");
  expect(within(nav).queryByRole("link", { name: "Modèles" })).not.toBeInTheDocument();
  expect(within(nav).getByRole("link", { name: "Abonnement" })).toBeInTheDocument();
});

it("compare les fonctions de chaque formule", async () => {
  setup("/fonctionnalites");
  const row = (await screen.findByRole("rowheader", { name: /SMS et WhatsApp/ })).closest("tr")!;
  const cells = within(row).getAllByRole("cell");
  expect(cells.map((c) => c.firstElementChild?.getAttribute("aria-label"))).toEqual([
    "Non inclus",
    "Non inclus",
    "Inclus",
  ]);
  expect(screen.getAllByText("Dès la formule Institution").length).toBeGreaterThan(0);
});
