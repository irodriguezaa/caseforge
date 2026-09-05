import { NextResponse } from "next/server";
import { proxyToBackend } from "@/lib/backend";

export async function GET(): Promise<NextResponse> {
  const response = await proxyToBackend("/api/v1/auth/me");
  const body = await response.json().catch(() => ({}));
  return NextResponse.json(body, { status: response.status });
}
