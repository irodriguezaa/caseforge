import { NextRequest, NextResponse } from "next/server";
import { proxyToBackend } from "@/lib/backend";

export async function GET(request: NextRequest): Promise<NextResponse> {
  const response = await proxyToBackend(`/api/v1/operational-windows${request.nextUrl.search}`);
  const body = await response.json();
  return NextResponse.json(body, { status: response.status });
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  const payload = await request.json();
  const response = await proxyToBackend("/api/v1/operational-windows", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  return NextResponse.json(body, { status: response.status });
}
