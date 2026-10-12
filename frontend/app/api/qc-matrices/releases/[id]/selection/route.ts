import { NextRequest, NextResponse } from "next/server";
import { proxyToBackend } from "@/lib/backend";

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ id: string }> },
): Promise<NextResponse> {
  const { id } = await context.params;
  const payload = await request.text();
  const response = await proxyToBackend(`/api/v1/qc-matrices/releases/${id}/selection`, {
    method: "POST",
    body: payload,
  });
  const body = await response.json();
  return NextResponse.json(body, { status: response.status });
}
