import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { tokenStore } from "./lib/tokens";
import { createAppRouter } from "./router";

const me = {
  id: "u1",
  email: "awa@example.org",
  full_name: "Awa Diallo",
  is_active: true,
  organizations: [
    {
      id: "org-1",
      name: "Solidarité Kivu",
      slug: "solidarite-kivu",
      default_language: "fr",
      created_at: "2026-09-27T10:00:00Z",
      role: "admin",
    },
  ],
};

const project = {
  id: "p1",
  code: "RES-01",
  title: "Résilience des ménages",
  description: "",
  donor: "UE",
  start_date: null,
  end_date: null,
  currency: "USD",
  language: "fr",
  status: "active",
  zones: [],
  target_groups: [],
  created_at: "2026-09-27T10:00:00Z",
};

const logframe = [
  {
    id: "n1",
    parent_id: null,
    level: "goal",
    code: "OG",
    title: "Réduire la vulnérabilité",
    description: "",
    assumptions: "",
    position: 0,
    children: [],
  },
];

const routes: [RegExp, unknown][] = [
  [/\/auth\/login$/, { access_token: "a", refresh_token: "r" }],
  [/\/auth\/me$/, me],
  [/\/projects$/, [project]],
  [/\/projects\/p1$/, project],
  [/\/logframe$/, logframe],
  [
    /\/logframe\/check$/,
    {
      nodes_without_indicator: logframe,
      indicators_without_source: [],
      activities_without_budget: [],
    },
  ],
  [/\/indicators$/, []],
];

function respond(url: string): Response {
  const body = routes.find(([pattern]) => pattern.test(url))?.[1] ?? [];
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  tokenStore.set(null);
});

it("connecte l'utilisateur puis ouvre le cadre logique d'un projet", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => Promise.resolve(respond(url))),
  );
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createAppRouter(queryClient, createMemoryHistory({ initialEntries: ["/"] }));

  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );

  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Adresse e-mail"), "awa@example.org");
  await user.type(screen.getByLabelText("Mot de passe"), "motdepasse1");
  await user.click(screen.getByRole("button", { name: "Se connecter" }));

  expect(await screen.findByRole("heading", { name: "Projets" })).toBeInTheDocument();
  expect(router.state.location.pathname).toBe("/orgs/org-1");

  await user.click(await screen.findByText("Résilience des ménages"));
  expect(await screen.findByText("Réduire la vulnérabilité")).toBeInTheDocument();
  expect(router.state.location.pathname).toBe("/orgs/org-1/projects/p1");
  expect(screen.getByRole("button", { name: "Cadre logique" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  expect(await screen.findByText("⚠ Sans indicateur")).toBeInTheDocument();
});
