import { NextRequest, NextResponse } from "next/server";
import { proxyToBackend } from "@/lib/backend";

interface RouteParams {
  params: Promise<{ view: string }>;
}

export async function GET(request: NextRequest, { params }: RouteParams): Promise<NextResponse> {
  const { view } = await params;
  if (view !== "day" && view !== "week") {
    return NextResponse.json({ detail: "view must be day or week" }, { status: 404 });
  }
  const response = await proxyToBackend(
    `/api/v1/calendar/${view}${request.nextUrl.search}`,
    undefined,
    { timeoutMs: 20_000 },
  );
  const body = await response.json();
  return NextResponse.json(body, { status: response.status });
}
