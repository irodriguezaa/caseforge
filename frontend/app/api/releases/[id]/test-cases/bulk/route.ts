import { NextRequest, NextResponse } from "next/server";

const backendUrl = process.env.BACKEND_URL ?? "http://backend:8000";
// Same reasoning as qc-tickets/bulk: large imports shouldn't be bound by the shared 5s
// CRUD-sized proxy default.
const bulkImportTimeoutMs = 120_000;

interface RouteParams {
  params: Promise<{ id: string }>;
}

export async function POST(request: NextRequest, { params }: RouteParams): Promise<NextResponse> {
  const { id } = await params;
  const payload = await request.json();
  try {
    const response = await fetch(`${backendUrl}/api/v1/releases/${id}/test-cases/bulk`, {
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
