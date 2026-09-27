import Dexie, { liveQuery, type Table } from "dexie";
import { useEffect, useState } from "react";

import {
  accountabilityApi,
  ApiError,
  type EvidenceInput,
  type ExecutionInput,
  executionsApi,
  type FeedbackIn,
  type SubmissionInput,
} from "./api";
import { formsApi } from "./formsApi";

/**
 * File d'envoi hors ligne. Toute saisie terrain y est d'abord enregistrée, puis envoyée dès que
 * le réseau le permet. Chaque élément porte un client_uuid : l'API reconnaît un renvoi et ne
 * crée pas de doublon, même si une réponse s'est perdue en route.
 */

export interface PendingExecution {
  client_uuid: string;
  orgId: string;
  projectId: string;
  body: ExecutionInput;
  createdAt: number;
  error?: string;
}

export interface PendingEvidence {
  client_uuid: string;
  orgId: string;
  projectId: string;
  // L'une ou l'autre : l'exécution peut elle-même attendre d'être envoyée.
  execution_client_uuid?: string;
  execution_id?: string;
  // Contenu brut plutôt qu'un Blob : certains navigateurs stockent mal les Blob en IndexedDB.
  data: ArrayBuffer;
  type: string;
  size: number;
  filename: string;
  meta: EvidenceInput;
  createdAt: number;
  error?: string;
}

export interface PendingFeedback {
  client_uuid: string;
  orgId: string;
  projectId: string;
  body: FeedbackIn;
  createdAt: number;
  error?: string;
}

export interface PendingSubmission {
  client_uuid: string;
  orgId: string;
  projectId: string;
  formId: string;
  body: SubmissionInput;
  createdAt: number;
  error?: string;
}

class OutboxDb extends Dexie {
  executions!: Table<PendingExecution, string>;
  evidence!: Table<PendingEvidence, string>;
  feedback!: Table<PendingFeedback, string>;
  submissions!: Table<PendingSubmission, string>;

  constructor() {
    super("wemeal-outbox");
    this.version(1).stores({
      executions: "client_uuid, projectId",
      evidence: "client_uuid, projectId, execution_client_uuid, execution_id",
    });
    // Plaintes et retours recueillis sans réseau (réunion communautaire, visite de terrain).
    this.version(2).stores({ feedback: "client_uuid, projectId" });
    // Réponses aux formulaires de collecte (enquêtes, suivi post-distribution).
    this.version(3).stores({ submissions: "client_uuid, projectId, formId" });
  }
}

export const outbox = new OutboxDb();

export const newId = () => crypto.randomUUID();

export interface FileToSend {
  file: Blob;
  filename: string;
  meta: EvidenceInput;
}

async function toStored(item: FileToSend) {
  return {
    client_uuid: item.meta.client_uuid,
    data: await readAsArrayBuffer(item.file),
    type: item.file.type,
    size: item.file.size,
    filename: item.filename,
    meta: item.meta,
  };
}

function readAsArrayBuffer(blob: Blob): Promise<ArrayBuffer> {
  if (typeof blob.arrayBuffer === "function") return blob.arrayBuffer();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as ArrayBuffer);
    reader.onerror = () => reject(reader.error);
    reader.readAsArrayBuffer(blob);
  });
}

export async function queueExecution(
  orgId: string,
  projectId: string,
  body: ExecutionInput,
  files: FileToSend[],
): Promise<void> {
  const createdAt = Date.now();
  const stored = await Promise.all(files.map(toStored));
  await outbox.transaction("rw", outbox.executions, outbox.evidence, async () => {
    await outbox.executions.put({
      client_uuid: body.client_uuid,
      orgId,
      projectId,
      body,
      createdAt,
    });
    await outbox.evidence.bulkPut(
      stored.map((item) => ({
        ...item,
        orgId,
        projectId,
        execution_client_uuid: body.client_uuid,
        createdAt,
      })),
    );
  });
}

export async function queueEvidence(
  orgId: string,
  projectId: string,
  executionId: string,
  files: FileToSend[],
): Promise<void> {
  const createdAt = Date.now();
  const stored = await Promise.all(files.map(toStored));
  await outbox.evidence.bulkPut(
    stored.map((item) => ({ ...item, orgId, projectId, execution_id: executionId, createdAt })),
  );
}

export async function queueFeedback(orgId: string, projectId: string, body: FeedbackIn) {
  await outbox.feedback.put({
    client_uuid: body.client_uuid,
    orgId,
    projectId,
    body,
    createdAt: Date.now(),
  });
}

export async function queueSubmission(
  orgId: string,
  projectId: string,
  formId: string,
  body: SubmissionInput,
) {
  await outbox.submissions.put({
    client_uuid: body.client_uuid,
    orgId,
    projectId,
    formId,
    body,
    createdAt: Date.now(),
  });
}

/** Erreur définitive (données refusées) : inutile de réessayer telle quelle. */
const isRejected = (error: unknown) =>
  error instanceof ApiError && error.status >= 400 && error.status < 500 && error.status !== 401;

export interface SyncResult {
  sent: number;
  rejected: number;
  offline: boolean;
}

let running: Promise<SyncResult> | null = null;

async function runSync(): Promise<SyncResult> {
  const result: SyncResult = { sent: 0, rejected: 0, offline: false };
  const attempt = async (
    send: () => Promise<void>,
    markError: (message: string) => Promise<unknown>,
  ) => {
    try {
      await send();
      result.sent += 1;
      return true;
    } catch (error) {
      if (isRejected(error)) {
        result.rejected += 1;
        await markError((error as ApiError).message);
        return true;
      }
      // Réseau coupé, serveur injoignable ou session expirée : on réessaiera plus tard.
      result.offline = true;
      return false;
    }
  };

  const byAge = <T extends { createdAt: number }>(items: T[]) =>
    items.sort((a, b) => a.createdAt - b.createdAt);

  for (const item of byAge(await outbox.feedback.toArray())) {
    if (item.error) continue;
    const ok = await attempt(
      async () => {
        await accountabilityApi.addFeedback(item.orgId, item.projectId, item.body);
        await outbox.feedback.delete(item.client_uuid);
      },
      (message) => outbox.feedback.update(item.client_uuid, { error: message }),
    );
    if (!ok) return result;
  }

  for (const item of byAge(await outbox.submissions.toArray())) {
    if (item.error) continue;
    const ok = await attempt(
      async () => {
        await formsApi.submit(item.orgId, item.projectId, item.formId, item.body);
        await outbox.submissions.delete(item.client_uuid);
      },
      (message) => outbox.submissions.update(item.client_uuid, { error: message }),
    );
    if (!ok) return result;
  }

  for (const item of byAge(await outbox.executions.toArray())) {
    if (item.error) continue;
    const ok = await attempt(
      async () => {
        const created = await executionsApi.create(item.orgId, item.projectId, item.body);
        await outbox.transaction("rw", outbox.executions, outbox.evidence, async () => {
          await outbox.evidence
            .where("execution_client_uuid")
            .equals(item.client_uuid)
            .modify({ execution_id: created.id });
          await outbox.executions.delete(item.client_uuid);
        });
      },
      (message) => outbox.executions.update(item.client_uuid, { error: message }),
    );
    if (!ok) return result;
  }

  for (const item of byAge(await outbox.evidence.toArray())) {
    if (item.error || !item.execution_id) continue;
    const executionId = item.execution_id;
    const ok = await attempt(
      async () => {
        await executionsApi.upload(
          item.orgId,
          item.projectId,
          executionId,
          new Blob([item.data], { type: item.type }),
          item.filename,
          item.meta,
        );
        await outbox.evidence.delete(item.client_uuid);
      },
      (message) => outbox.evidence.update(item.client_uuid, { error: message }),
    );
    if (!ok) return result;
  }
  return result;
}

/** Envoie tout ce qui attend ; un seul envoi à la fois. */
export function syncOutbox(): Promise<SyncResult> {
  running ??= runSync().finally(() => {
    running = null;
  });
  return running;
}

export async function discard(
  table: "executions" | "evidence" | "feedback" | "submissions",
  clientUuid: string,
) {
  if (table === "feedback" || table === "submissions") {
    await outbox[table].delete(clientUuid);
  } else if (table === "executions") {
    await outbox.transaction("rw", outbox.executions, outbox.evidence, async () => {
      await outbox.evidence.where("execution_client_uuid").equals(clientUuid).delete();
      await outbox.executions.delete(clientUuid);
    });
  } else {
    await outbox.evidence.delete(clientUuid);
  }
}

export interface Pending {
  executions: PendingExecution[];
  evidence: PendingEvidence[];
  feedback: PendingFeedback[];
  submissions: PendingSubmission[];
}

/** Éléments en attente pour un projet, mis à jour en direct. */
export function usePending(projectId: string): Pending {
  const [pending, setPending] = useState<Pending>({
    executions: [],
    evidence: [],
    feedback: [],
    submissions: [],
  });
  useEffect(() => {
    const subscription = liveQuery(async () => ({
      executions: await outbox.executions.where("projectId").equals(projectId).toArray(),
      evidence: await outbox.evidence.where("projectId").equals(projectId).toArray(),
      feedback: await outbox.feedback.where("projectId").equals(projectId).toArray(),
      submissions: await outbox.submissions.where("projectId").equals(projectId).toArray(),
    })).subscribe({ next: setPending, error: () => undefined });
    return () => subscription.unsubscribe();
  }, [projectId]);
  return pending;
}
