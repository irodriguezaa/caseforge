import { NextResponse } from "next/server";

const backendUrl = process.env.BACKEND_URL ?? "http://backend:8000";
const healthCheckTimeoutMs = 5_000;

export async function GET(): Promise<NextResponse> {
  try {
    const response = await fetch(`${backendUrl}/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(healthCheckTimeoutMs),
    });
    const body: unknown = await response.json();
    return NextResponse.json(body, { status: response.status });
  } catch {
    return NextResponse.json(
      { status: "error", service: "backend", message: "Backend unavailable" },
      { status: 503 },
    );
  }
}
