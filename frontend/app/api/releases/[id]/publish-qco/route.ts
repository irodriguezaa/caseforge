import { NextRequest, NextResponse } from "next/server";
import { idAfterDrain, proxyToBackend } from "@/lib/backend";

/** QCO_ZEPHYR_PUBLISH — BFF kept; UI gated by SHOW_QCO_ZEPHYR_PUBLISH. */
export async function POST(
  request: NextRequest,
  context: { params: Promise<{ id: string }> }
): Promise<NextResponse> {
  const id = await idAfterDrain(request, context.params);
  const response = await proxyToBackend(
    `/api/v1/releases/${id}/publish-qco`,
    { method: "POST" },
    { timeoutMs: 600_000 },
  );
  const body = await response.json();
  return NextResponse.json(body, { status: response.status });
}
