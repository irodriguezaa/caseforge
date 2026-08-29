import { NextRequest, NextResponse } from "next/server";
import { proxyToBackend } from "@/lib/backend";

interface RouteParams {
  params: Promise<{ id: string }>;
}

export async function POST(request: NextRequest, { params }: RouteParams): Promise<NextResponse> {
  const { id } = await params;
  const payload = await request.json();
  const response = await proxyToBackend(`/api/v1/releases/${id}/windows`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  return NextResponse.json(body, { status: response.status });
}
