import { NextRequest, NextResponse } from "next/server";
import { proxyToBackend } from "@/lib/backend";

export async function GET(request: NextRequest): Promise<NextResponse> {
  const response = await proxyToBackend(`/api/v1/releases${request.nextUrl.search}`);
  const body = await response.json();
  return NextResponse.json(body, { status: response.status });
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  const payload = await request.text();
  const response = await proxyToBackend("/api/v1/releases", {
    method: "POST",
    body: payload,
  });
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
}
