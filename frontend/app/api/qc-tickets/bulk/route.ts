import { NextRequest, NextResponse } from "next/server";

const backendUrl = process.env.BACKEND_URL ?? "http://backend:8000";
// Bulk imports can carry thousands of rows (a real Jira export); the shared 5s proxy default
// (lib/backend.ts) is tuned for small CRUD calls and was very likely why a 2435-row import
// failed with a proxy timeout. This route gets its own, much longer budget instead.
const bulkImportTimeoutMs = 120_000;

export async function POST(request: NextRequest): Promise<NextResponse> {
  const payload = await request.json();
  try {
    const response = await fetch(`${backendUrl}/api/v1/qc-tickets/bulk`, {
      method: "POST",
      body: JSON.stringify(payload),
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      signal: AbortSignal.timeout(bulkImportTimeoutMs),
    });
    const body = await response.json();
    return NextResponse.json(body, { status: response.status });
  } catch {
    return NextResponse.json({ status: "error", message: "Backend unavailable" }, { status: 503 });
  }
}
