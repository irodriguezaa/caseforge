import { NextRequest, NextResponse } from "next/server";
import { fetchBackend } from "@/lib/backend";

const requestTimeoutMs = 15_000;

export async function POST(request: NextRequest): Promise<NextResponse> {
  try {
    const incomingFormData = await request.formData();
    const response = await fetchBackend(
      "/api/v1/operativa/analyze-rn",
      { method: "POST", body: incomingFormData },
      { timeoutMs: requestTimeoutMs },
    );
    const body = await response.json();
    return NextResponse.json(body, { status: response.status });
  } catch {
    return NextResponse.json({ status: "error", message: "Backend unavailable" }, { status: 503 });
  }
}
