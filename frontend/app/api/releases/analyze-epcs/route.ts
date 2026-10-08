import { NextRequest, NextResponse } from "next/server";
import { backendUnavailableResponse, fetchBackend } from "@/lib/backend";

const requestTimeoutMs = 180_000;

export async function POST(request: NextRequest): Promise<NextResponse> {
  try {
    const payload = await request.text();
    const response = await fetchBackend(
      "/api/v1/releases/analyze-epcs",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: payload,
      },
      { timeoutMs: requestTimeoutMs },
    );
    const body = await response.json();
    return NextResponse.json(body, { status: response.status });
  } catch (err) {
    const fallback = backendUnavailableResponse(err);
    return new NextResponse(fallback.body, {
      status: fallback.status,
      headers: fallback.headers,
    });
  }
}
