import { NextRequest, NextResponse } from "next/server";
import { idAndBody, proxyToBackend } from "@/lib/backend";

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ id: string }> },
): Promise<NextResponse> {
  const { id, body } = await idAndBody(request, context.params);
  const response = await proxyToBackend(
    `/api/v1/releases/${id}/jira-epic`,
    { method: "POST", body },
    { timeoutMs: 60_000 },
  );
  const payload = await response.json().catch(() => ({ detail: "Jira no respondió." }));
  return NextResponse.json(payload, { status: response.status });
}
