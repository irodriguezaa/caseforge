import { NextRequest, NextResponse } from "next/server";
import { drainBody, fetchBackend, passThroughAuth } from "@/lib/backend";

export async function POST(request: NextRequest): Promise<NextResponse> {
  try {
    await drainBody(request);
    const response = await fetchBackend("/api/v1/auth/logout", { method: "POST" });
    return passThroughAuth(response);
  } catch {
    return NextResponse.json({ detail: "Backend unavailable" }, { status: 503 });
  }
}
