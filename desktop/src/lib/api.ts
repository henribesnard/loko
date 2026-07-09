/**
 * LOKO — HTTP API client.
 *
 * Wraps fetch() for the FastAPI backend.
 * Authentication: session cookie (HttpOnly, set by /api/auth/login).
 * For ops super-admin: Bearer token via sessionStorage.
 */

const BASE = "";

// -- Ops admin token (super-admin only, /ops routes) --
const OPS_STORAGE_KEY = "loko_ops_auth";

export function getOpsToken(): string | null {
  return sessionStorage.getItem(OPS_STORAGE_KEY);
}

export function setOpsToken(token: string): void {
  sessionStorage.setItem(OPS_STORAGE_KEY, token);
}

export function clearOpsToken(): void {
  sessionStorage.removeItem(OPS_STORAGE_KEY);
}

// -- Legacy admin token compatibility (kept for backward compat during migration) --
const STORAGE_KEY = "loko_auth";

export function getAdminToken(): string | null {
  return sessionStorage.getItem(STORAGE_KEY);
}

export function setAdminToken(token: string): void {
  sessionStorage.setItem(STORAGE_KEY, token);
}

export function clearAdminToken(): void {
  sessionStorage.removeItem(STORAGE_KEY);
}

function authHeaders(): Record<string, string> {
  // Try ops token first (for /api/ops routes), then legacy admin token
  const ops = getOpsToken();
  if (ops) return { Authorization: `Bearer ${ops}` };
  const admin = getAdminToken();
  return admin ? { Authorization: `Bearer ${admin}` } : {};
}

export async function api<T = unknown>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...options.headers,
    },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new ApiError(res.status, body, path);
  }
  return res.json() as Promise<T>;
}

export async function apiStream(
  path: string,
  body: unknown,
): Promise<ReadableStream<Uint8Array>> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new ApiError(res.status, text, path);
  }
  return res.body!;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: string,
    public path: string,
  ) {
    super(`API ${status} on ${path}: ${body}`);
  }
}
