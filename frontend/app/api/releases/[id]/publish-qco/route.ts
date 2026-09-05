import { NextRequest, NextResponse } from "next/server";
import { proxyToBackend } from "@/lib/backend";

/** QCO_ZEPHYR_PUBLISH — BFF kept; UI gated by SHOW_QCO_ZEPHYR_PUBLISH. */
export async function POST(
  _request: NextRequest,
  context: { params: Promise<{ id: string }> }
): Promise<NextResponse> {
  const { id } = await context.params;
  const response = await proxyToBackend(
    `/api/v1/releases/${id}/publish-qco`,
    { method: "POST" },
    { timeoutMs: 600_000 },
  );
  const body = await response.json();
  return NextResponse.json(body, { status: response.status });
}
