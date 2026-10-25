import { afterEach, beforeEach, expect, it, vi } from "vitest";

import type { ExecutionInput } from "./api";
import {
  countPending,
  newId,
  outbox,
  purgeOutbox,
  queueExecution,
  queueFeedback,
  syncOutbox,
} from "./outbox";
import { tokenStore } from "./tokens";

const body = (): ExecutionInput => ({
  activity_id: "a1",
  title: "Formation",
  start_date: "2026-03-14",
  end_date: null,
  location: "Kiwanja",
  latitude: null,
  longitude: null,
  participants: { women: 2, men: 1, girls: 0, boys: 0, with_disability: 0 },
  notes: "",
  status: "completed",
  client_uuid: newId(),
});

const photo = () => ({
  file: new Blob(["jpeg"], { type: "image/jpeg" }),
  filename: "photo.jpg",
  meta: { kind: "photo" as const, caption: "", consent_given: true, client_uuid: newId() },
});

beforeEach(async () => {
  tokenStore.set({ access_token: "a", refresh_token: "r" });
  await outbox.executions.clear();
  await outbox.evidence.clear();
  await outbox.feedback.clear();
  await outbox.submissions.clear();
});
afterEach(() => vi.restoreAllMocks());

it("keeps entries while offline, then sends execution before its files", async () => {
  const execution = body();
  await queueExecution("o", "p", execution, [photo()]);

  vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
  expect(await syncOutbox()).toEqual({ sent: 0, rejected: 0, offline: true });
  expect(await outbox.executions.count()).toBe(1);

  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(new Response(JSON.stringify({ id: "exe-1" }), { status: 201 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ id: "ev-1" }), { status: 201 }));
  fetch.mockClear();
  expect(await syncOutbox()).toEqual({ sent: 2, rejected: 0, offline: false });

  const [first, second] = fetch.mock.calls;
  expect(first[0]).toBe("/api/v1/orgs/o/projects/p/executions");
  expect(JSON.parse(first[1]!.body as string).client_uuid).toBe(execution.client_uuid);
  expect(second[0]).toBe("/api/v1/orgs/o/projects/p/executions/exe-1/evidence");
  expect((second[1]!.body as FormData).get("kind")).toBe("photo");
  expect(await outbox.executions.count()).toBe(0);
  expect(await outbox.evidence.count()).toBe(0);
});

it("marks refused entries instead of retrying them forever", async () => {
  await queueExecution("o", "p", body(), []);
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ detail: "Seule une activité peut être exécutée" }), {
      status: 422,
    }),
  );
  expect(await syncOutbox()).toEqual({ sent: 0, rejected: 1, offline: false });
  const [entry] = await outbox.executions.toArray();
  expect(entry.error).toBe("Seule une activité peut être exécutée");
  expect(await syncOutbox()).toEqual({ sent: 0, rejected: 0, offline: false });
});

it("sends feedback recorded offline once the network is back", async () => {
  const feedback = {
    received_on: "2026-03-17",
    channel: "community_meeting" as const,
    category: "complaint" as const,
    description: "Les séances commencent trop tard.",
    location: "Kiwanja",
    activity_id: null,
    anonymous: true,
    contact: "",
    client_uuid: newId(),
  };
  await queueFeedback("o", "p", feedback);
  vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
  expect(await syncOutbox()).toEqual({ sent: 0, rejected: 0, offline: true });
  expect(await outbox.feedback.count()).toBe(1);

  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(new Response(JSON.stringify({ id: "f-1" }), { status: 201 }));
  fetch.mockClear();
  expect(await syncOutbox()).toEqual({ sent: 1, rejected: 0, offline: false });
  expect(fetch.mock.calls[0][0]).toBe("/api/v1/orgs/o/projects/p/feedback");
  expect(JSON.parse(fetch.mock.calls[0][1]!.body as string).client_uuid).toBe(feedback.client_uuid);
  expect(await outbox.feedback.count()).toBe(0);
});

/** Jeton d'accès au format JWT dont seul le champ `sub` compte ici. */
const tokensFor = (userId: string) => ({
  access_token: `h.${btoa(JSON.stringify({ sub: userId }))}.s`,
  refresh_token: "r",
});

it("never sends one agent's entries with another agent's account", async () => {
  tokenStore.set(tokensFor("agent-a"));
  await queueExecution("o", "p", body(), [photo()]);
  expect((await outbox.executions.toArray())[0].userId).toBe("agent-a");

  tokenStore.set(tokensFor("agent-b"));
  const fetch = vi.spyOn(globalThis, "fetch");
  expect(await syncOutbox()).toEqual({ sent: 0, rejected: 0, offline: false });
  expect(fetch).not.toHaveBeenCalled();
  expect(await outbox.executions.count()).toBe(1);

  tokenStore.set(tokensFor("agent-a"));
  fetch
    .mockResolvedValueOnce(new Response(JSON.stringify({ id: "exe-1" }), { status: 201 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ id: "ev-1" }), { status: 201 }));
  expect(await syncOutbox()).toEqual({ sent: 2, rejected: 0, offline: false });
});

it("empties the whole queue when the session ends", async () => {
  await queueExecution("o", "p", body(), [photo()]);
  await queueFeedback("o", "p", {
    received_on: "2026-03-17",
    channel: "hotline",
    category: "fraud",
    description: "Signalement",
    location: "",
    activity_id: null,
    anonymous: false,
    contact: "+243 000 000",
    client_uuid: newId(),
  });
  expect(await countPending()).toBe(3);
  await purgeOutbox();
  expect(await countPending()).toBe(0);
});
