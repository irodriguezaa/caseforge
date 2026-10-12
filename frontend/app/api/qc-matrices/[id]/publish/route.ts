import { NextResponse } from "next/server";
import { proxyToBackend } from "@/lib/backend";

export async function POST(
  _request: Request,
  context: { params: Promise<{ id: string }> },
): Promise<NextResponse> {
  const { id } = await context.params;
  const response = await proxyToBackend(`/api/v1/qc-matrices/${id}/publish`, { method: "POST" });
  const body = await response.json();
  return NextResponse.json(body, { status: response.status });
}
