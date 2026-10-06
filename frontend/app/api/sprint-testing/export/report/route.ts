import { NextRequest, NextResponse } from "next/server";
import { proxyToBackend } from "@/lib/backend";

export const dynamic = "force-dynamic";
export const maxDuration = 180;

function errorDetail(body: unknown): string {
  if (!body || typeof body !== "object") {
    return "No se pudo exportar.";
  }
  const record = body as { detail?: unknown; message?: unknown };
  if (typeof record.detail === "string" && record.detail.trim()) {
    return record.detail;
  }
  if (typeof record.message === "string" && record.message.trim()) {
    return record.message;
  }
  return "No se pudo exportar.";
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  const { search } = new URL(request.url);
  const response = await proxyToBackend(`/api/v1/sprint-testing/export/report${search}`, { method: "GET" }, {
    timeoutMs: 180_000,
  });
  const contentType = response.headers.get("Content-Type") ?? "";
  if (!response.ok) {
    const body = contentType.includes("application/json")
      ? await response.json().catch(() => ({}))
      : { detail: await response.text().catch(() => "No se pudo exportar.") };
    return NextResponse.json({ detail: errorDetail(body) }, { status: response.status });
  }
  if (
    !contentType.includes("presentation") &&
    !contentType.includes("octet-stream") &&
    !contentType.includes("powerpoint")
  ) {
    const body = await response.json().catch(() => ({}));
    return NextResponse.json(
      { detail: errorDetail(body) || "El servidor no devolvió un PowerPoint." },
      { status: 502 },
    );
  }
  const buffer = await response.arrayBuffer();
  return new NextResponse(buffer, {
    status: 200,
    headers: {
      "Content-Type":
        contentType || "application/vnd.openxmlformats-officedocument.presentationml.presentation",
      "Content-Length": String(buffer.byteLength),
      "Content-Disposition":
        response.headers.get("Content-Disposition") ?? 'attachment; filename="Sprint_ejecutivo.pptx"',
    },
  });
}
