import { NextRequest, NextResponse } from "next/server";
import { idAndBody, proxyToBackend } from "@/lib/backend";

interface RouteParams {
  params: Promise<{ id: string }>;
}

export async function GET(_request: NextRequest, { params }: RouteParams): Promise<NextResponse> {
  const { id } = await params;
  const response = await proxyToBackend(`/api/v1/releases/${id}`);
  const body = await response.json();
  return NextResponse.json(body, { status: response.status });
}

export async function PATCH(request: NextRequest, { params }: RouteParams): Promise<NextResponse> {
  const { id, body } = await idAndBody(request, params);
  console.info(`[bff] PATCH /api/v1/releases/${id} bytes=${body.length}`);
  const response = await proxyToBackend(`/api/v1/releases/${id}`, {
    method: "PATCH",
    body,
  });
  console.info(`[bff] PATCH /api/v1/releases/${id} -> ${response.status}`);
  const payload = await response.json();
  return NextResponse.json(payload, { status: response.status });
}

export async function DELETE(
  _request: NextRequest,
  { params }: RouteParams,
): Promise<NextResponse> {
  const { id } = await params;
  const response = await proxyToBackend(`/api/v1/releases/${id}`, { method: "DELETE" });
  if (response.status === 204) {
    return new NextResponse(null, { status: 204 });
  }
  const body = await response.json();
  return NextResponse.json(body, { status: response.status });
}
