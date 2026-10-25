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
    if (url.origin !== origin) return null;
    // Re-check what is returned: dot-segment normalization turns "/..//evil.test" into "//evil.test".
    const path = `${url.pathname}${url.search}${url.hash}`;
    return path.startsWith("/") && !path.startsWith("//") ? path : null;
  } catch {
    return null;
  }
}

/** Sign-in URL that returns to the current page afterwards (consumed by safeNext on the sign-in page). */
export function signInUrl(): string {
  if (typeof window === "undefined") return "/sign-in";
  return `/sign-in?next=${encodeURIComponent(`${window.location.pathname}${window.location.search}`)}`;
}

export function clearSession() {
  localStorage.removeItem(key);
  cachedRaw = null;
  cachedSession = null;
}
