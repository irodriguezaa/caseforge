/**
 * Shared helper for Next.js API routes that proxy to the FastAPI backend (BFF pattern).
 * Mirrors the approach already used by app/api/health/route.ts and app/api/health/db/route.ts
 * from Sprint 1: the browser never calls the backend directly, only these internal routes do,
 * since only server-side code can resolve the `backend` hostname on the Docker network.
 */

const backendUrl = process.env.BACKEND_URL ?? "http://backend:8000";
const requestTimeoutMs = 5_000;

export async function proxyToBackend(path: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(`${backendUrl}${path}`, {
      ...init,
      cache: "no-store",
      signal: AbortSignal.timeout(requestTimeoutMs),
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    return new Response(
      JSON.stringify({ status: "error", message: "Backend unavailable" }),
      { status: 503, headers: { "Content-Type": "application/json" } },
    );
  }
}
