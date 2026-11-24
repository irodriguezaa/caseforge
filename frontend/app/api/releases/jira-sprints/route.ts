import { NextResponse } from "next/server";
import { backendUnavailableResponse, fetchBackend } from "@/lib/backend";

export async function GET(): Promise<NextResponse> {
  try {
    const response = await fetchBackend("/api/v1/releases/jira-sprints", { method: "GET" });
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
