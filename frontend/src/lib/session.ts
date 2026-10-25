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

/** Where to go after signing in: only same-site paths, so a crafted link cannot bounce users off-site. */
export function safeNext(value: string | null | undefined): string | null {
  return value && value.startsWith("/") && !value.startsWith("//") && !value.startsWith("/\\") ? value : null;
}

export function clearSession() {
  localStorage.removeItem(key);
  cachedRaw = null;
  cachedSession = null;
}
