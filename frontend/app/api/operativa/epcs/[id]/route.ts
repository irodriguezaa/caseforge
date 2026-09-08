import { NextRequest, NextResponse } from "next/server";
import { idAndBody, proxyToBackend } from "@/lib/backend";

interface RouteParams {
  params: Promise<{ id: string }>;
}

export async function PATCH(request: NextRequest, { params }: RouteParams): Promise<NextResponse> {
  const { id, body } = await idAndBody(request, params);
  const response = await proxyToBackend(`/api/v1/operativa/epcs/${id}`, { method: "PATCH", body });
  const responseBody = await response.json();
  return NextResponse.json(responseBody, { status: response.status });
}
