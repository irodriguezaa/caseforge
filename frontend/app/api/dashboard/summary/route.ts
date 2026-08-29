import { NextResponse } from "next/server";
import { proxyToBackend } from "@/lib/backend";

export async function GET(): Promise<NextResponse> {
  const response = await proxyToBackend("/api/v1/dashboard/summary");
  const body = await response.json();
  return NextResponse.json(body, { status: response.status });
}
