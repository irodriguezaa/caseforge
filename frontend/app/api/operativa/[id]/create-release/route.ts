import { NextRequest, NextResponse } from "next/server";
import { idAfterDrain, proxyToBackend } from "@/lib/backend";

interface RouteParams {
  params: Promise<{ id: string }>;
}

export async function POST(request: NextRequest, { params }: RouteParams): Promise<NextResponse> {
  const id = await idAfterDrain(request, params);
  const response = await proxyToBackend(`/api/v1/operativa/${id}/create-release`, { method: "POST" });
  const body = await response.json();
  return NextResponse.json(body, { status: response.status });
}
