export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
export const SITE_NAME = process.env.NEXT_PUBLIC_SITE_NAME ?? "TixGH";

export class ApiError extends Error {
  constructor(public status: number, public data: unknown) {
    super(errorMessage(data, status));
  }
}

/** Turn DRF error bodies ({detail}, {field: [msg]}, {problems: [...]}) into one readable line. */
export function errorMessage(data: unknown, status = 0): string {
  if (!data || typeof data !== "object") return status >= 500 ? "Something went wrong. Please try again." : "Request failed.";
  const d = data as Record<string, unknown>;
  if (Array.isArray(d.problems) && d.problems.length) return `${d.detail ?? ""} ${(d.problems as string[]).join(" ")}`.trim();
  if (typeof d.detail === "string") return d.detail;
  for (const [key, val] of Object.entries(d)) {
    const first = Array.isArray(val) ? val[0] : val;
    if (typeof first === "string") return key === "non_field_errors" ? first : `${first}`;
    if (first && typeof first === "object") return errorMessage(first, status);
  }
  return "Request failed.";
}

type FetchOpts = {
  method?: string;
  body?: unknown;
  token?: string | null;
  revalidate?: number | false;
};

export async function apiFetch<T>(path: string, opts: FetchOpts = {}): Promise<T> {
  const isForm = typeof FormData !== "undefined" && opts.body instanceof FormData;
  const headers: Record<string, string> = { Accept: "application/json" };
  if (opts.body !== undefined && !isForm) headers["Content-Type"] = "application/json";
  if (opts.token) headers.Authorization = `Bearer ${opts.token}`;
  const init: RequestInit & { next?: { revalidate: number | false } } = {
    method: opts.method ?? (opts.body !== undefined ? "POST" : "GET"),
    headers,
    body: opts.body === undefined ? undefined : isForm ? (opts.body as FormData) : JSON.stringify(opts.body),
  };
  if (opts.revalidate !== undefined) init.next = { revalidate: opts.revalidate };
  else if (typeof window === "undefined") init.cache = "no-store";

  const res = await fetch(`${API_URL}/api/v1${path}`, init);
  if (res.status === 204 || res.status === 205) return undefined as T;
  const text = await res.text();
  const data = text ? safeJson(text) : null;
  if (!res.ok) throw new ApiError(res.status, data);
  return data as T;
}

function safeJson(text: string) {
  try {
    return JSON.parse(text);
  } catch {
    return { detail: text.slice(0, 200) };
  }
}

/** Media URLs may come back relative (/media/...) from some endpoints. */
export function mediaUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  return url.startsWith("http") ? url : `${API_URL}${url}`;
}
