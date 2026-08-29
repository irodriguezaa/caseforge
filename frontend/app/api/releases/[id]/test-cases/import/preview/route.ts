import { NextRequest, NextResponse } from "next/server";

const backendUrl = process.env.BACKEND_URL ?? "http://backend:8000";
const importTimeoutMs = 15_000;

interface RouteParams {
  params: Promise<{ id: string }>;
}

/**
 * Unlike the other proxy routes, this one forwards multipart/form-data, so it deliberately does
 * NOT use lib/backend.ts's proxyToBackend helper (which always sets a JSON content-type). Letting
 * fetch build its own FormData/boundary here keeps the multipart body intact end to end.
 */
export async function POST(request: NextRequest, { params }: RouteParams): Promise<NextResponse> {
  const { id } = await params;

  try {
    const incomingFormData = await request.formData();
    const response = await fetch(`${backendUrl}/api/v1/releases/${id}/test-cases/import/preview`, {
      method: "POST",
      body: incomingFormData,
      cache: "no-store",
      signal: AbortSignal.timeout(importTimeoutMs),
    });
    const body = await response.json();
    return NextResponse.json(body, { status: response.status });
  } catch {
    return NextResponse.json(
      { status: "error", message: "Backend unavailable" },
      { status: 503 },
    );
  }
}
