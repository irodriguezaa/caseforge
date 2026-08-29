import { NextRequest, NextResponse } from "next/server";
import { proxyToBackend } from "@/lib/backend";

export async function POST(
  _request: NextRequest,
  context: { params: Promise<{ id: string }> }
): Promise<NextResponse> {
  const { id } = await context.params;
  const response = await proxyToBackend(`/api/v1/releases/${id}/generate-cases`, {
    method: "POST",
  });
  const body = await response.json();
  return NextResponse.json(body, { status: response.status });
}
