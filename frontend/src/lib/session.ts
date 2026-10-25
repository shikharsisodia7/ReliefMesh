export type SessionUser = { id: string; email?: string; role: "coordinator" | "supplier" };

const key = "reliefmesh.session";
let cachedRaw: string | null | undefined;
let cachedSession: { token: string; user: SessionUser } | null = null;

export function saveSession(token: string, user: SessionUser) {
  const serialized = JSON.stringify({ token, user });
  cachedRaw = serialized;
  cachedSession = { token, user };
  localStorage.setItem(key, serialized);
}

export function readSession(): { token: string; user: SessionUser } | null {
  if (typeof window === "undefined") return null;
  const stored = localStorage.getItem(key);
  if (stored === cachedRaw) return cachedSession;
  cachedRaw = stored;
  if (!stored) { cachedSession = null; return null; }
  try {
    cachedSession = JSON.parse(stored);
    return cachedSession;
  } catch {
    localStorage.removeItem(key);
    cachedRaw = null;
    cachedSession = null;
    return null;
  }
}

/** Where to go after signing in: only same-site paths, so a crafted link cannot bounce users off-site.
 * Control characters and backslashes are rejected outright (browsers strip or rewrite them, turning a
 * tab between the two slashes into "//evil.test"); the rest is resolved by the URL parser and must stay
 * on this origin. */
export function safeNext(value: string | null | undefined): string | null {
  if (!value || !value.startsWith("/") || /[\u0000-\u001F\u007F\\]/.test(value)) return null;
  try {
    const origin = typeof window === "undefined" ? "http://localhost" : window.location.origin;
    const url = new URL(value, origin);
    return url.origin === origin ? `${url.pathname}${url.search}${url.hash}` : null;
  } catch {
    return null;
  }
}

export function clearSession() {
  localStorage.removeItem(key);
  cachedRaw = null;
  cachedSession = null;
}
