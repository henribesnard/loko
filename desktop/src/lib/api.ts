/**
 * LOKO — HTTP API client.
 *
 * T3: Session cookie is the primary auth for /api/bot and /api/auth.
 * S6: CSRF double-submit cookie for mutating requests.
 * Ops admin token (Bearer) is used only for /api/ops routes.
 */

const BASE = "";

// -- Ops admin token (super-admin only, /api/ops routes) --
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

// S6: Read CSRF token from cookie
function getCsrfToken(): string | null {
  const match = document.cookie.match(/(?:^|; )csrf_token=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : null;
}

function buildHeaders(path: string, method: string): Record<string, string> {
  const headers: Record<string, string> = {};

  // T3: Only send ops token for /api/ops routes
  if (path.startsWith("/api/ops")) {
    const ops = getOpsToken();
    if (ops) headers["Authorization"] = `Bearer ${ops}`;
  }

  // S6: Add CSRF header for mutating requests
  const safeMethods = ["GET", "HEAD", "OPTIONS"];
  if (!safeMethods.includes(method.toUpperCase())) {
    const csrf = getCsrfToken();
    if (csrf) headers["X-CSRF-Token"] = csrf;
  }

  return headers;
}

export async function api<T = unknown>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const method = (options.method || "GET").toUpperCase();
  const res = await fetch(`${BASE}${path}`, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...buildHeaders(path, method),
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
    headers: {
      "Content-Type": "application/json",
      ...buildHeaders(path, "POST"),
    },
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
