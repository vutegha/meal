import { QueryClient } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";

import { meQuery } from "./queries";
import { endSession, loadProfile, startSession } from "./session";
import { tokenStore } from "./tokens";

const tokensFor = (userId: string) => ({
  access_token: `h.${btoa(JSON.stringify({ sub: userId }))}.s`,
  refresh_token: "r",
});

const me = (id: string) => ({
  id,
  email: `${id}@example.org`,
  full_name: id,
  is_active: true,
  organizations: [],
});

const ok = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });

const client = () => new QueryClient({ defaultOptions: { queries: { retry: false } } });

afterEach(async () => {
  vi.unstubAllGlobals();
  await endSession(client());
});

it("ouvre l'application hors ligne avec le profil gardé sur l'appareil", async () => {
  await startSession(client(), tokensFor("u1"));
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(ok(me("u1"))));
  await loadProfile(client());

  // Réouverture sans réseau : nouvelle mémoire, appel à /auth/me impossible.
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
  const offline = client();
  expect(await loadProfile(offline)).toMatchObject({ id: "u1" });
  expect(offline.getQueryData(meQuery.queryKey)).toMatchObject({ id: "u1" });
  expect(tokenStore.get()).not.toBeNull();
});

it("ne reprend pas le profil d'un autre compte", async () => {
  await startSession(client(), tokensFor("u1"));
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(ok(me("u1"))));
  await loadProfile(client());

  await startSession(client(), tokensFor("u2"));
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
  await expect(loadProfile(client())).rejects.toBeInstanceOf(TypeError);
});

it("ferme la session quand le serveur la refuse", async () => {
  await startSession(client(), tokensFor("u1"));
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ detail: "invalide" }), { status: 401 })),
  );
  expect(await loadProfile(client())).toBeNull();
  expect(tokenStore.get()).toBeNull();
});
