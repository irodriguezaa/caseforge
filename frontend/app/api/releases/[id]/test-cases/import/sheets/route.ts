import { NextRequest, NextResponse } from "next/server";
import { fetchBackend } from "@/lib/backend";

const requestTimeoutMs = 15_000;

interface RouteParams {
  params: Promise<{ id: string }>;
}

export async function POST(request: NextRequest, { params }: RouteParams): Promise<NextResponse> {
  const { id } = await params;

  try {
    const incomingFormData = await request.formData();
    const response = await fetchBackend(
      `/api/v1/releases/${id}/test-cases/import/sheets`,
      { method: "POST", body: incomingFormData },
      { timeoutMs: requestTimeoutMs },
    );
    const body = await response.json();
    return NextResponse.json(body, { status: response.status });
  } catch {
    return NextResponse.json(
      { status: "error", message: "Backend unavailable" },
      { status: 503 },
    );
  }
}
