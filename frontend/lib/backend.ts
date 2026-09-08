/**
 * Shared helper for Next.js API routes that proxy to the FastAPI backend (BFF pattern).
 * Mirrors the approach already used by app/api/health/route.ts and app/api/health/db/route.ts
 * from Sprint 1: the browser never calls the backend directly, only these internal routes do,
 * since only server-side code can resolve the `backend` hostname on the Docker network.
 */

import { cookies } from "next/headers";
import { NextResponse } from "next/server";

const backendUrl = process.env.BACKEND_URL ?? "http://backend:8000";
const defaultTimeoutMs = 30_000;

export async function cookieHeaderFromSession(): Promise<string | null> {
  const store = await cookies();
  const all = store.getAll();
  if (all.length === 0) {
    return null;
  }
  return all.map((cookie) => `${cookie.name}=${cookie.value}`).join("; ");
}

export async function fetchBackend(
  path: string,
  init?: RequestInit,
  options?: { timeoutMs?: number },
): Promise<Response> {
  const headers = new Headers(init?.headers);
  const cookieHeader = await cookieHeaderFromSession();
  if (cookieHeader && !headers.has("Cookie")) {
    headers.set("Cookie", cookieHeader);
  }
  return fetch(`${backendUrl}${path}`, {
    ...init,
    headers,
    cache: "no-store",
    signal: AbortSignal.timeout(options?.timeoutMs ?? defaultTimeoutMs),
  });
}

export async function proxyToBackend(
  path: string,
  init?: RequestInit,
  options?: { timeoutMs?: number },
): Promise<Response> {
  try {
    const headers = new Headers(init?.headers);
    const hasBody = init?.body != null && init.body !== "";
    if (hasBody && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    return await fetchBackend(path, { ...init, headers }, options);
  } catch {
    return new Response(
      JSON.stringify({ status: "error", message: "Backend unavailable" }),
      { status: 503, headers: { "Content-Type": "application/json" } },
    );
  }
}

export async function passThroughAuth(response: Response): Promise<NextResponse> {
  const contentType = response.headers.get("Content-Type") ?? "application/json";
  const body = await response.arrayBuffer();
  const next = new NextResponse(body, {
    status: response.status,
    headers: { "Content-Type": contentType },
  });
  const setCookies =
    typeof response.headers.getSetCookie === "function"
      ? response.headers.getSetCookie()
      : [];
  for (const cookie of setCookies) {
    next.headers.append("Set-Cookie", cookie);
  }
  return next;
}
