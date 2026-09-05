import { NextResponse } from "next/server";
import { proxyToBackend } from "@/lib/backend";

export async function GET(): Promise<NextResponse> {
  const response = await proxyToBackend("/api/v1/operativa");
  const body = await response.json();
  return NextResponse.json(body, { status: response.status });
}
