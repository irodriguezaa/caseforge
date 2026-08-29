import { NextRequest, NextResponse } from "next/server";

const backendUrl = process.env.BACKEND_URL ?? "http://backend:8000";
const requestTimeoutMs = 30_000;

export async function POST(request: NextRequest): Promise<NextResponse> {
  try {
    const incomingFormData = await request.formData();
    const response = await fetch(`${backendUrl}/api/v1/releases/analyze-rn`, {
      method: "POST",
      body: incomingFormData,
      cache: "no-store",
      signal: AbortSignal.timeout(requestTimeoutMs),
    });
    const body = await response.json();
    return NextResponse.json(body, { status: response.status });
  } catch {
    return NextResponse.json({ status: "error", message: "Backend unavailable" }, { status: 503 });
  }
}
