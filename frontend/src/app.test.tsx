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

function respond(url: string): Response {
  const body = url.endsWith("/auth/login")
    ? { access_token: "a", refresh_token: "r" }
    : url.endsWith("/auth/me")
      ? me
      : url.endsWith("/members")
        ? [{ id: "m1", role: "admin", user: me, created_at: "2026-09-27T10:00:00Z" }]
        : [];
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  tokenStore.set(null);
});

it("redirige vers la connexion puis ouvre le tableau de bord de l'organisation", async () => {
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

  expect(
    await screen.findByRole("heading", { name: "Bienvenue dans Solidarité Kivu" }),
  ).toBeInTheDocument();
  expect(screen.getByText("Votre rôle : Administrateur")).toBeInTheDocument();
  expect(await screen.findByText("Membres")).toBeInTheDocument();
  expect(router.state.location.pathname).toBe("/orgs/org-1");
});
