import { NextRequest, NextResponse } from "next/server";

const backendUrl = process.env.BACKEND_URL ?? "http://backend:8000";
const requestTimeoutMs = 15_000;

interface RouteParams {
  params: Promise<{ id: string }>;
}

/**
 * Like the sibling import/preview route, this forwards multipart/form-data as-is -- it must
 * NOT use lib/backend.ts's proxyToBackend helper, which always sets a JSON content-type.
 */
export async function POST(request: NextRequest, { params }: RouteParams): Promise<NextResponse> {
  const { id } = await params;

  try {
    const incomingFormData = await request.formData();
    const response = await fetch(`${backendUrl}/api/v1/releases/${id}/test-cases/import/sheets`, {
      method: "POST",
      body: incomingFormData,
      cache: "no-store",
      signal: AbortSignal.timeout(requestTimeoutMs),
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
