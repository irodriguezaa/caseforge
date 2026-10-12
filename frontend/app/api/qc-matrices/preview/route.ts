import { NextRequest, NextResponse } from "next/server";
import { proxyToBackend } from "@/lib/backend";

export async function POST(request: NextRequest): Promise<NextResponse> {
  const payload = await request.text();
  const response = await proxyToBackend("/api/v1/qc-matrices/preview", { method: "POST", body: payload });
  const body = await response.json();
  return NextResponse.json(body, { status: response.status });
}
