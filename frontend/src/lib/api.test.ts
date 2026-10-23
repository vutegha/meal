import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError } from "./api";
import { tokenStore } from "./tokens";

const jsonResponse = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

afterEach(() => {
  vi.unstubAllGlobals();
  tokenStore.set(null);
});

describe("api.request", () => {
  it("rafraîchit le jeton après un 401 puis rejoue la requête", async () => {
    tokenStore.set({ access_token: "expire", refresh_token: "r1" });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(401, { detail: "Authentification requise" }))
      .mockResolvedValueOnce(jsonResponse(200, { access_token: "neuf", refresh_token: "r2" }))
      .mockResolvedValueOnce(jsonResponse(200, { id: "u1", organizations: [] }));
    vi.stubGlobal("fetch", fetchMock);

    const me = await api.me();

    expect(me).toEqual({ id: "u1", organizations: [] });
    expect(tokenStore.get()).toEqual({ access_token: "neuf", refresh_token: "r2" });
    const replay = fetchMock.mock.calls[2] as [string, RequestInit];
    expect(new Headers(replay[1].headers).get("Authorization")).toBe("Bearer neuf");
  });

  it("vide la session si le rafraîchissement échoue", async () => {
    tokenStore.set({ access_token: "expire", refresh_token: "expire" });
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(jsonResponse(401, { detail: "Authentification requise" }))
        .mockResolvedValueOnce(jsonResponse(401, { detail: "invalide" })),
    );

    await expect(api.me()).rejects.toBeInstanceOf(ApiError);
    expect(tokenStore.get()).toBeNull();
  });

  it("garde la session si le réseau coupe pendant le rafraîchissement", async () => {
    const tokens = { access_token: "expire", refresh_token: "r1" };
    tokenStore.set(tokens);
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(jsonResponse(401, { detail: "Authentification requise" }))
        .mockRejectedValueOnce(new TypeError("Failed to fetch")),
    );

    await expect(api.me()).rejects.toBeInstanceOf(TypeError);
    expect(tokenStore.get()).toEqual(tokens);
  });

  it("garde la session si le serveur est indisponible pendant le rafraîchissement", async () => {
    const tokens = { access_token: "expire", refresh_token: "r1" };
    tokenStore.set(tokens);
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(jsonResponse(401, { detail: "Authentification requise" }))
        .mockResolvedValueOnce(jsonResponse(502, { detail: "Passerelle" })),
    );

    await expect(api.me()).rejects.toMatchObject({ status: 502 });
    expect(tokenStore.get()).toEqual(tokens);
  });

  it("remonte le message d'erreur du serveur", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse(401, { detail: "Identifiants invalides" })),
    );
    await expect(api.login("a@b.org", "x")).rejects.toThrow("Identifiants invalides");
  });
});
