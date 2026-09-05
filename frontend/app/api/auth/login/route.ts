import { NextRequest, NextResponse } from "next/server";
import { fetchBackend, passThroughAuth } from "@/lib/backend";

export async function POST(request: NextRequest): Promise<NextResponse> {
  try {
    const body = await request.text();
    const response = await fetchBackend("/api/v1/auth/login", {
      method: "POST",
      body,
      headers: { "Content-Type": "application/json" },
    });
    return passThroughAuth(response);
  } catch {
    return NextResponse.json({ detail: "Backend unavailable" }, { status: 503 });
  }
}
