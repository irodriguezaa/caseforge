import { NextRequest, NextResponse } from "next/server";
import { proxyToBackend } from "@/lib/backend";

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ id: string }> }
): Promise<NextResponse> {
  const { id } = await context.params;
  const search = request.nextUrl.search || "";
  const response = await proxyToBackend(
    `/api/v1/releases/${id}/generate-cases${search}`,
    { method: "POST" },
    { timeoutMs: 180_000 },
  );
  const body = await response.json();
  return NextResponse.json(body, { status: response.status });
}
