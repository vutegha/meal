export interface Tokens {
  access_token: string;
  refresh_token: string;
}

const KEY = "wemeal.tokens";
const listeners = new Set<() => void>();

function read(): Tokens | null {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Tokens) : null;
  } catch {
    return null;
  }
}

let current: Tokens | null = read();

/** Identifiant de l'utilisateur porté par le jeton d'accès (champ `sub`), sans appel réseau. */
export function userIdOf(tokens: Tokens | null): string | null {
  const payload = tokens?.access_token.split(".")[1];
  if (!payload) return null;
  try {
    const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    const sub = (JSON.parse(json) as { sub?: unknown }).sub;
    return typeof sub === "string" ? sub : null;
  } catch {
    return null;
  }
}

export const tokenStore = {
  get: (): Tokens | null => current,
  userId: (): string | null => userIdOf(current),
  set(tokens: Tokens | null) {
    current = tokens;
    try {
      if (tokens) localStorage.setItem(KEY, JSON.stringify(tokens));
      else localStorage.removeItem(KEY);
    } catch {
      // Stockage indisponible (navigation privée) : la session reste en mémoire.
    }
    listeners.forEach((listener) => listener());
  },
  subscribe(listener: () => void) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
};
