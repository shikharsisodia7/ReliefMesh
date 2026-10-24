export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type ApiError = Error & { status?: number; code?: string };

function describe(detail: unknown): { message: string; code?: string } {
  if (typeof detail === "string") return { message: detail };
  if (Array.isArray(detail)) return { message: detail.map((row) => (row as { msg?: string }).msg ?? JSON.stringify(row)).join("; ") };
  if (detail && typeof detail === "object") {
    const record = detail as { message?: string; code?: string };
    return { message: record.code ? `${record.code}: ${record.message ?? ""}` : record.message ?? JSON.stringify(detail), code: record.code };
  }
  return { message: "The request could not be completed." };
}

export async function api<T>(
  path: string,
  options: RequestInit & { token?: string } = {},
): Promise<T> {
  const { token, headers, ...requestOptions } = options;
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...requestOptions,
    headers: {
      ...(requestOptions.body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const { message, code } = describe(payload.detail ?? payload.error);
    const error = new Error(message) as ApiError;
    error.status = response.status;
    error.code = code;
    throw error;
  }
  return response.json() as Promise<T>;
}
