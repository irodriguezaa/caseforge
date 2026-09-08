import { NextRequest, NextResponse } from "next/server";
import { drainBody, proxyToBackend } from "@/lib/backend";

export async function GET(): Promise<NextResponse> {
  const response = await proxyToBackend("/api/v1/releases-be");
  const body = await response.json();
  return NextResponse.json(body, { status: response.status });
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  await drainBody(request);
  const response = await proxyToBackend("/api/v1/releases-be", { method: "POST" });
  const body = await response.json();
  return NextResponse.json(body, { status: response.status });
}
