import { NextResponse } from "next/server";
import { fetchBackend } from "@/lib/backend";

export const dynamic = "force-dynamic";

export async function GET(): Promise<NextResponse> {
  try {
    const response = await fetchBackend("/api/v1/llm/health", { method: "GET" }, { timeoutMs: 25_000 });
    const body: unknown = await response.json().catch(() => ({}));
    return NextResponse.json(body, { status: response.status });
  } catch {
    return NextResponse.json(
      { status: "error", service: "llm", message: "Backend unavailable" },
      { status: 503 },
    );
  }
}
