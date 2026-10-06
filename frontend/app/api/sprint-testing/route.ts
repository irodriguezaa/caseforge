import { NextResponse } from "next/server";
import { proxyToBackend } from "@/lib/backend";

export async function GET(request: Request): Promise<NextResponse> {
  const { search } = new URL(request.url);
  try {
    const response = await proxyToBackend(`/api/v1/sprint-testing${search}`, undefined, {
      timeoutMs: 120_000,
    });
    const body = await response.json();
    return NextResponse.json(body, { status: response.status });
  } catch {
    return NextResponse.json({ detail: "Backend no disponible" }, { status: 503 });
  }
}
