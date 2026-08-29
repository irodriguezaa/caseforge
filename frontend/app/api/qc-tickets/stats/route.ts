import { NextRequest, NextResponse } from "next/server";
import { proxyToBackend } from "@/lib/backend";

export async function GET(request: NextRequest): Promise<NextResponse> {
  const response = await proxyToBackend(`/api/v1/qc-tickets/stats${request.nextUrl.search}`);
  const body = await response.json();
  return NextResponse.json(body, { status: response.status });
}
