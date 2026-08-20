/**
 * Thin client for the shared FastAPI. Every website data call goes through
 * here so auth, errors, and the base URL are handled in one place.
 *
 * The base URL comes from NEXT_PUBLIC_API_URL (see .env.local.example).
 */

// Default to the same-origin "/api" path, which the Next dev server proxies to
// the backend (see next.config.mjs). This avoids CORS and the Windows
// localhost/IPv6 mismatch entirely. In production, set NEXT_PUBLIC_API_URL to
// the real API URL and calls go direct.
const BASE = process.env.NEXT_PUBLIC_API_URL ?? "/api";

const TOKEN_KEY = "asw_access_token";
// Fail fast instead of hanging forever if the API/cloud is unreachable. Data
// calls get 30s; file downloads (server-built PDF/Excel) get 90s.
const TIMEOUT_MS = 30000;
const DOWNLOAD_TIMEOUT_MS = 90000;

/** fetch() with an AbortController timeout that maps a timeout to a clear error. */
async function fetchWithTimeout(url: string, init: RequestInit, ms: number): Promise<Response> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), ms);
  try {
    return await fetch(url, { ...init, signal: ctrl.signal });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") {
      throw new ApiError(0, "The server took too long to respond. Check your connection and try again.");
    }
    throw new ApiError(0, "Couldn't reach the server. Check your connection.");
  } finally {
    clearTimeout(timer);
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: { method?: string; body?: unknown } = {},
): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetchWithTimeout(`${BASE}${path}`, {
    method: options.method ?? "GET",
    headers,
    body: options.body != null ? JSON.stringify(options.body) : undefined,
  }, TIMEOUT_MS);

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      if (data?.detail) detail = data.detail;
    } catch {
      /* non-JSON error body — keep the status text */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** GET a file with the auth header and hand it to the browser to save. */
async function download(path: string, filename: string): Promise<void> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetchWithTimeout(`${BASE}${path}`, { headers }, DOWNLOAD_TIMEOUT_MS);
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}

/** POST a browser-picked file as multipart/form-data (auth header, no JSON). */
async function upload<T>(path: string, file: File): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const form = new FormData();
  form.append("file", file);
  const res = await fetchWithTimeout(`${BASE}${path}`, { method: "POST", headers, body: form }, TIMEOUT_MS);
  if (!res.ok) {
    let detail = res.statusText;
    try { const d = await res.json(); if (d?.detail) detail = d.detail; } catch { /* keep */ }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  download,
  upload,
};
