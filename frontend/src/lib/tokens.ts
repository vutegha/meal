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

export const tokenStore = {
  get: (): Tokens | null => current,
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
