import { NextRequest, NextResponse } from "next/server";
import { proxyToBackend } from "@/lib/backend";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ id: string }> },
): Promise<NextResponse> {
  const { id } = await context.params;
  const brf = request.nextUrl.searchParams.get("brf_key") ?? request.nextUrl.searchParams.get("brf");
  const query = brf ? `?brf_key=${encodeURIComponent(brf)}` : "";
  const response = await proxyToBackend(
    `/api/v1/releases/${id}/coverage-matrix/preview${query}`,
    { method: "GET" },
    { timeoutMs: 180_000 },
  );
  const body = await response.json();
  return NextResponse.json(body, { status: response.status });
}
