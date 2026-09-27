import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "./api";
import { client, unwrap } from "./client";
import { tokenStore } from "./tokens";

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

afterEach(() => {
  vi.unstubAllGlobals();
  tokenStore.set(null);
});

describe("client généré", () => {
  it("envoie le jeton et réessaie après rafraîchissement", async () => {
    tokenStore.set({ access_token: "ancien", refresh_token: "r" });
    const seen: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: Request | string) => {
        if (typeof input === "string") {
          // Rafraîchissement par le client historique.
          expect(input).toBe("/api/v1/auth/refresh");
          return json(200, { access_token: "neuf", refresh_token: "r2" });
        }
        seen.push(input.headers.get("Authorization") ?? "");
        return seen.length === 1 ? json(401, { detail: "expiré" }) : json(200, []);
      }),
    );
    const forms = await unwrap(
      client.GET("/api/v1/orgs/{org_id}/projects/{project_id}/forms", {
        baseUrl: "http://localhost",
        params: { path: { org_id: "o", project_id: "p" } },
      }),
    );
    expect(forms).toEqual([]);
    expect(seen).toEqual(["Bearer ancien", "Bearer neuf"]);
    expect(tokenStore.get()?.access_token).toBe("neuf");
  });

  it("transmet le message d'erreur du serveur", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json(409, { detail: "Formulaire clôturé" })),
    );
    const call = unwrap(
      client.GET("/api/v1/orgs/{org_id}/projects/{project_id}/forms", {
        baseUrl: "http://localhost",
        params: { path: { org_id: "o", project_id: "p" } },
      }),
    );
    await expect(call).rejects.toEqual(new ApiError(409, "Formulaire clôturé"));
  });
});
