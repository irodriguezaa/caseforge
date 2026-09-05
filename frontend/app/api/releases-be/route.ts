import { NextResponse } from "next/server";
import { proxyToBackend } from "@/lib/backend";

export async function GET(): Promise<NextResponse> {
  const response = await proxyToBackend("/api/v1/releases-be");
  const body = await response.json();
  return NextResponse.json(body, { status: response.status });
}

export async function POST(): Promise<NextResponse> {
  const response = await proxyToBackend("/api/v1/releases-be", { method: "POST" });
  const body = await response.json();
  return NextResponse.json(body, { status: response.status });
}
