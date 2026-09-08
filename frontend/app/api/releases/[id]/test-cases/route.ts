import { NextRequest, NextResponse } from "next/server";
import { idAndBody, proxyToBackend } from "@/lib/backend";

interface RouteParams {
  params: Promise<{ id: string }>;
}

export async function GET(request: NextRequest, { params }: RouteParams): Promise<NextResponse> {
  const { id } = await params;
  const response = await proxyToBackend(
    `/api/v1/releases/${id}/test-cases${request.nextUrl.search}`,
  );
  const body = await response.json();
  return NextResponse.json(body, { status: response.status });
}

export async function POST(request: NextRequest, { params }: RouteParams): Promise<NextResponse> {
  const { id, body } = await idAndBody(request, params);
  const response = await proxyToBackend(`/api/v1/releases/${id}/test-cases`, {
    method: "POST",
    body,
  });
  const payload = await response.json();
  return NextResponse.json(payload, { status: response.status });
}
