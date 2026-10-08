import { NextRequest, NextResponse } from "next/server";
import { backendUnavailableResponse, idAfterDrain, proxyToBackend } from "@/lib/backend";

export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ id: string }> },
): Promise<NextResponse> {
  try {
    const id = await idAfterDrain(request, context.params);
    const response = await proxyToBackend(
      `/api/v1/releases/${id}/generate-cases/status`,
      { method: "GET" },
      { timeoutMs: 15_000 },
    );
    const raw = await response.text();
    let body: unknown = {};
    if (raw) {
      try {
        body = JSON.parse(raw) as unknown;
      } catch {
        body = { detail: raw.slice(0, 200) };
      }
    }
    return NextResponse.json(body, { status: response.status });
  } catch (err) {
    const fallback = backendUnavailableResponse(err);
    return new NextResponse(fallback.body, {
      status: fallback.status,
      headers: fallback.headers,
    });
  }
}
