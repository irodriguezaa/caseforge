import { NextRequest, NextResponse } from "next/server";
import { backendUnavailableResponse, fetchBackend } from "@/lib/backend";

export async function POST(request: NextRequest): Promise<NextResponse> {
  try {
    const incoming = await request.formData();
    const response = await fetchBackend("/api/v1/qc-matrices/import", { method: "POST", body: incoming }, { timeoutMs: 120_000 });
    const body = await response.json();
    return NextResponse.json(body, { status: response.status });
  } catch (err) {
    const fallback = backendUnavailableResponse(err);
    return new NextResponse(fallback.body, { status: fallback.status, headers: fallback.headers });
  }
}
