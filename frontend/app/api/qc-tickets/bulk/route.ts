import { NextRequest, NextResponse } from "next/server";
import { fetchBackend } from "@/lib/backend";

const bulkImportTimeoutMs = 120_000;

export async function POST(request: NextRequest): Promise<NextResponse> {
  const payload = await request.json();
  try {
    const response = await fetchBackend(
      "/api/v1/qc-tickets/bulk",
      { method: "POST", body: JSON.stringify(payload), headers: { "Content-Type": "application/json" } },
      { timeoutMs: bulkImportTimeoutMs },
    );
    const body = await response.json();
    return NextResponse.json(body, { status: response.status });
  } catch {
    return NextResponse.json({ status: "error", message: "Backend unavailable" }, { status: 503 });
  }
}
