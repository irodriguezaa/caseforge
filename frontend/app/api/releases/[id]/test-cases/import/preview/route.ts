import { NextRequest, NextResponse } from "next/server";
import { fetchBackend, idAndFormData } from "@/lib/backend";

const importTimeoutMs = 15_000;

interface RouteParams {
  params: Promise<{ id: string }>;
}

export async function POST(request: NextRequest, { params }: RouteParams): Promise<NextResponse> {
  const { id, formData } = await idAndFormData(request, params);

  try {
    const response = await fetchBackend(
      `/api/v1/releases/${id}/test-cases/import/preview`,
      { method: "POST", body: formData },
      { timeoutMs: importTimeoutMs },
    );
    const body = await response.json();
    return NextResponse.json(body, { status: response.status });
  } catch {
    return NextResponse.json(
      { status: "error", message: "Backend unavailable" },
      { status: 503 },
    );
  }
}
