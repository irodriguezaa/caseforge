import { NextResponse } from "next/server";
import { proxyToBackend } from "@/lib/backend";

export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> },
): Promise<NextResponse> {
  const { id } = await context.params;
  const response = await proxyToBackend(`/api/v1/qc-matrices/${id}`);
  const body = await response.json();
  return NextResponse.json(body, { status: response.status });
}
