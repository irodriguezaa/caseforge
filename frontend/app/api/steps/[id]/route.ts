import { NextRequest, NextResponse } from "next/server";
import { idAndBody, proxyToBackend } from "@/lib/backend";

interface RouteParams {
  params: Promise<{ id: string }>;
}

export async function PATCH(request: NextRequest, { params }: RouteParams): Promise<NextResponse> {
  const { id, body } = await idAndBody(request, params);
  const response = await proxyToBackend(`/api/v1/steps/${id}`, {
    method: "PATCH",
    body,
  });
  const body = await response.json();
  return NextResponse.json(body, { status: response.status });
}

export async function DELETE(
  _request: NextRequest,
  { params }: RouteParams,
): Promise<NextResponse> {
  const { id } = await params;
  const response = await proxyToBackend(`/api/v1/steps/${id}`, { method: "DELETE" });
  if (response.status === 204) {
    return new NextResponse(null, { status: 204 });
  }
  const body = await response.json();
  return NextResponse.json(body, { status: response.status });
}
