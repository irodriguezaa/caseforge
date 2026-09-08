import { NextRequest, NextResponse } from "next/server";
import { proxyToBackend } from "@/lib/backend";

interface RouteParams {
  params: Promise<{ id: string }>;
}

export async function POST(_request: NextRequest, { params }: RouteParams): Promise<NextResponse> {
  const { id } = await params;
  const response = await proxyToBackend(
    `/api/v1/releases-be/${id}/create-release`,
    { method: "POST" },
    { timeoutMs: 60_000 },
  );
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
