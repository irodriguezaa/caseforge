import { NextResponse } from "next/server";
import { fetchBackend, passThroughAuth } from "@/lib/backend";

export async function POST(): Promise<NextResponse> {
  try {
    const response = await fetchBackend("/api/v1/auth/logout", { method: "POST" });
    return passThroughAuth(response);
  } catch {
    return NextResponse.json({ detail: "Backend unavailable" }, { status: 503 });
  }
}
