import { API_URL } from "./config";

export class ApiError extends Error {
  constructor(public status: number, public data: unknown) {
    super(errorMessage(data, status));
  }
}

export function errorMessage(data: unknown, status = 0): string {
  if (!data || typeof data !== "object") return status >= 500 ? "Server error. Please try again." : "Request failed.";
  const d = data as Record<string, unknown>;
  if (typeof d.detail === "string") return d.detail;
  for (const val of Object.values(d)) {
    const first = Array.isArray(val) ? val[0] : val;
    if (typeof first === "string") return first;
    if (first && typeof first === "object") return errorMessage(first, status);
  }
  return "Request failed.";
}

export type FetchOpts = { method?: string; body?: unknown; token?: string | null; timeoutMs?: number };

export async function apiFetch<T>(path: string, opts: FetchOpts = {}): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), opts.timeoutMs ?? 20000);
  try {
    const res = await fetch(`${API_URL}/api/v1${path}`, {
      method: opts.method ?? (opts.body !== undefined ? "POST" : "GET"),
      headers: {
        Accept: "application/json",
        ...(opts.body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(opts.token ? { Authorization: `Bearer ${opts.token}` } : {}),
      },
      body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
      signal: controller.signal,
    });
    if (res.status === 204 || res.status === 205) return undefined as T;
    const text = await res.text();
    let data: unknown = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = { detail: text.slice(0, 200) };
    }
    if (!res.ok) throw new ApiError(res.status, data);
    return data as T;
  } finally {
    clearTimeout(timer);
  }
}

/** True for errors caused by no/slow network rather than a server answer. */
export function isNetworkError(e: unknown): boolean {
  return !(e instanceof ApiError);
}
