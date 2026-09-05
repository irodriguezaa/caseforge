import { NextRequest, NextResponse } from "next/server";
import { proxyToBackend } from "@/lib/backend";

interface RouteParams {
  params: Promise<{ id: string }>;
}

export async function PATCH(request: NextRequest, { params }: RouteParams): Promise<NextResponse> {
  const { id } = await params;
  const body = await request.text();
  const response = await proxyToBackend(`/api/v1/operativa/epcs/${id}`, { method: "PATCH", body });
  const responseBody = await response.json();
  return NextResponse.json(responseBody, { status: response.status });
}
