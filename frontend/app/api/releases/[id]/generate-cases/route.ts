import { NextRequest, NextResponse } from "next/server";
import { backendUnavailableResponse, idAfterDrain, proxyToBackend } from "@/lib/backend";

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ id: string }> }
): Promise<NextResponse> {
  try {
    const id = await idAfterDrain(request, context.params);
    const search = request.nextUrl.search || "";
    const response = await proxyToBackend(
      `/api/v1/releases/${id}/generate-cases${search}`,
      { method: "POST" },
      { timeoutMs: 600_000 },
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
