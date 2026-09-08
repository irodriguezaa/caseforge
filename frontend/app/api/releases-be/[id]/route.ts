import { NextRequest, NextResponse } from "next/server";
import { proxyToBackend } from "@/lib/backend";

interface RouteParams {
  params: Promise<{ id: string }>;
}

export async function GET(_request: NextRequest, { params }: RouteParams): Promise<NextResponse> {
  const { id } = await params;
  const response = await proxyToBackend(`/api/v1/releases-be/${id}`);
  const body = await response.json();
  return NextResponse.json(body, { status: response.status });
}

export async function PATCH(request: NextRequest, { params }: RouteParams): Promise<NextResponse> {
  const { id } = await params;
  const body = await request.text();
  const response = await proxyToBackend(`/api/v1/releases-be/${id}`, { method: "PATCH", body });
  const responseBody = await response.json();
  return NextResponse.json(responseBody, { status: response.status });
}

export async function DELETE(
  _request: NextRequest,
  { params }: RouteParams,
): Promise<NextResponse> {
  const { id } = await params;
  const response = await proxyToBackend(`/api/v1/releases-be/${id}`, { method: "DELETE" });
  if (response.status === 204) {
    return new NextResponse(null, { status: 204 });
  }
  const body = await response.json();
  return NextResponse.json(body, { status: response.status });
}
