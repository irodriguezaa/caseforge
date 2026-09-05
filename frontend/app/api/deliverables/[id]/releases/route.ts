import { NextRequest, NextResponse } from "next/server";
import { proxyToBackend } from "@/lib/backend";

interface RouteParams {
  params: Promise<{ id: string }>;
}

export async function GET(_request: NextRequest, { params }: RouteParams): Promise<NextResponse> {
  const { id } = await params;
  const response = await proxyToBackend(`/api/v1/deliverables/${id}/releases`);
  const body = await response.json();
  return NextResponse.json(body, { status: response.status });
}
