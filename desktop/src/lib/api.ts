/**
 * LOKO — HTTP API client.
 *
 * Wraps fetch() for the FastAPI backend.
 * In dev mode, requests are proxied via Vite (see vite.config.ts).
 */

const BASE = "";

export async function api<T = unknown>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
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
    headers: { "Content-Type": "application/json" },
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
