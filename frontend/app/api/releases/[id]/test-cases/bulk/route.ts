import { NextRequest, NextResponse } from "next/server";
import { fetchBackend } from "@/lib/backend";

const bulkImportTimeoutMs = 120_000;

interface RouteParams {
  params: Promise<{ id: string }>;
}

export async function POST(request: NextRequest, { params }: RouteParams): Promise<NextResponse> {
  const { id } = await params;
  const payload = await request.json();
  try {
    const response = await fetchBackend(
      `/api/v1/releases/${id}/test-cases/bulk`,
      { method: "POST", body: JSON.stringify(payload), headers: { "Content-Type": "application/json" } },
      { timeoutMs: bulkImportTimeoutMs },
    );
    const body = await response.json();
    return NextResponse.json(body, { status: response.status });
  } catch {
    return NextResponse.json({ status: "error", message: "Backend unavailable" }, { status: 503 });
  }
}
