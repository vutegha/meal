import type { QueryClient } from "@tanstack/react-query";

import { ApiError, type Me } from "./api";
import { purgeOutbox } from "./outbox";
import { meQuery } from "./queries";
import { type Tokens, tokenStore, userIdOf } from "./tokens";

/**
 * Session sur l'appareil. Le profil du dernier utilisateur est gardé pour que l'application
 * s'ouvre sans réseau sur le terrain ; tout ce qui lui appartient (profil, réponses d'API en
 * cache, file d'envoi) est effacé à la déconnexion ou quand un autre compte se connecte.
 */

const PROFILE_KEY = "wemeal.me";
// Réponses d'API gardées par le service worker (vite.config.ts).
const API_CACHE = "api";

function readProfile(): Me | null {
  try {
    const raw = localStorage.getItem(PROFILE_KEY);
    return raw ? (JSON.parse(raw) as Me) : null;
  } catch {
    return null;
  }
}

function writeProfile(me: Me | null) {
  try {
    if (me) localStorage.setItem(PROFILE_KEY, JSON.stringify(me));
    else localStorage.removeItem(PROFILE_KEY);
  } catch {
    // Stockage indisponible : l'ouverture hors ligne ne sera simplement pas possible.
  }
}

async function clearApiCache() {
  if (typeof caches !== "undefined") await caches.delete(API_CACHE);
}

/**
 * Profil de l'utilisateur connecté. Sans réseau (ou serveur indisponible), on reprend le
 * profil gardé sur l'appareil ; seule une session refusée par le serveur renvoie `null`.
 */
export async function loadProfile(queryClient: QueryClient): Promise<Me | null> {
  try {
    const me = await queryClient.ensureQueryData(meQuery);
    writeProfile(me);
    return me;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      tokenStore.set(null);
      return null;
    }
    const saved = readProfile();
    if (saved && saved.id === tokenStore.userId()) {
      queryClient.setQueryData(meQuery.queryKey, saved);
      return saved;
    }
    throw error;
  }
}

/** Ouvre une session ; les données d'un autre compte resté sur l'appareil sont effacées. */
export async function startSession(queryClient: QueryClient, tokens: Tokens) {
  const previous = readProfile();
  if (previous && previous.id !== userIdOf(tokens)) {
    writeProfile(null);
    queryClient.clear();
    await clearApiCache();
  }
  tokenStore.set(tokens);
}

/** Ferme la session et efface de l'appareil tout ce qui appartient à l'utilisateur. */
export async function endSession(queryClient: QueryClient) {
  tokenStore.set(null);
  writeProfile(null);
  queryClient.clear();
  await Promise.all([clearApiCache(), purgeOutbox()]);
}
