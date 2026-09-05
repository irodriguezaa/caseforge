import { NextRequest, NextResponse } from "next/server";
import { fetchBackend } from "@/lib/backend";

const jiraRefreshTimeoutMs = 120_000;

export async function POST(request: NextRequest): Promise<NextResponse> {
  try {
    const response = await fetchBackend(
      `/api/v1/qc-tickets/jira/refresh${request.nextUrl.search}`,
      { method: "POST", headers: { "Content-Type": "application/json" } },
      { timeoutMs: jiraRefreshTimeoutMs },
    );
    const body = await response.json();
    return NextResponse.json(body, { status: response.status });
  } catch {
    return NextResponse.json({ status: "error", message: "Backend unavailable" }, { status: 503 });
  }
}
