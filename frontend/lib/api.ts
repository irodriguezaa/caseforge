import type {
  ApiError,
  AuthUser,
  BeAnalysisResult,
  BeReleaseRead,
  BeReleaseUpdate,
  BulkCreateResult,
  DashboardSummary,
  Deliverable,
  DeliverableReleaseSummary,
  DeliverableWithMetrics,
  EpcRead,
  EpcUpdate,
  ImportCandidateTestCase,
  ImportPreviewResult,
  ImportSheetsResult,
  OperationalWindow,
  OperativaAnalysisResult,
  OperativaReleaseRead,
  OperativaReleaseUpdate,
  QcDashboardSummary,
  QcRadarConfigResponse,
  QcSummaryFilters,
  QcTicketBulkCreateResult,
  QcTicketCreate,
  QcTicketImportPreviewResult,
  QcTicketJiraRefreshResult,
  QcTicketRead,
  QcTicketSource,
  QcTicketStats,
  QcTicketView,
  CoverageMatrixResponse,
  GenerateCasesResponse,
  PublishCasesResponse,
  QcCalendarDayResponse,
  QcCalendarWeekResponse,
  Release,
  ReleaseKpisRead,
  ReleaseAnalysis,
  ReleaseNoteAnalyzeResponse,
  ReleaseStatus,
  ReleaseType,
  ReleaseWindow,
  ReleaseWithCounts,
  TestCase,
  TestCaseWithSteps,
  TestStep,
} from "@/lib/types";

export class ApiRequestError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

const BASE_PATH = "/qcpulse";

function apiUrl(path: string): string {
  return `${BASE_PATH}${path.startsWith("/") ? path : `/${path}`}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  const headers = new Headers(init?.headers);
  if (init?.body != null && init.body !== "" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  try {
    response = await fetch(apiUrl(path), {
      ...init,
      cache: "no-store",
      credentials: "include",
      headers,
    });
  } catch {
    throw new ApiRequestError(0, "No se pudo contactar el servidor. Reintenta en unos segundos.");
  }

  if (response.status === 401 && !path.startsWith("/api/auth")) {
    if (typeof window !== "undefined" && window.location.pathname !== apiUrl("/login")) {
      window.location.assign(apiUrl("/login"));
    }
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const body = (await response.json().catch(() => ({}))) as T & ApiError;

  if (!response.ok) {
    const raw = body?.detail ?? body?.message ?? `Request failed (${response.status})`;
    const message = typeof raw === "string" ? raw : JSON.stringify(raw);
    throw new ApiRequestError(response.status, message);
  }

  return body;
}

export interface ReleaseInput {
  name: string;
  version: string;
  platform: string;
  cluster?: string | null;
  description?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  qc_resources?: number | null;
  execution_days?: number | null;
  validation_type?: string | null;
  jira_issue_filter?: string | null;
  analysis_data?: ReleaseAnalysis | null;
  deliverable_name?: string | null;
  release_type?: ReleaseType | null;
  parent_release_id?: number | null;
}

export interface TestStepInput {
  step_number: number;
  test_step: string;
  expected_result: string;
}

export interface TestCaseInput {
  test_case_id: string;
  component: string;
  test_case_name: string;
  description?: string | null;
  user_type?: string | null;
  priority?: TestCase["priority"];
  test_type?: TestCase["test_type"];
  steps?: TestStepInput[];
}

export const api = {
  me: () => request<AuthUser>("/api/auth/me"),
  login: (email: string, password: string) =>
    request<AuthUser>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  logout: () => request<{ status: string }>("/api/auth/logout", { method: "POST" }),

  listReleases: (params?: {
    status?: ReleaseStatus;
    platform?: string;
    include_be?: boolean;
    include_operativa?: boolean;
  }) => {
    const query = new URLSearchParams();
    if (params?.status) query.set("status", params.status);
    if (params?.platform) query.set("platform", params.platform);
    if (params?.include_be) query.set("include_be", "true");
    if (params?.include_operativa) query.set("include_operativa", "true");
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return request<ReleaseWithCounts[]>(`/api/releases${suffix}`);
  },
  createRelease: (payload: ReleaseInput) =>
    request<Release>("/api/releases", { method: "POST", body: JSON.stringify(payload) }),
  getRelease: (id: number) => request<Release>(`/api/releases/${id}`),
  updateRelease: (id: number, payload: Partial<ReleaseInput & { status: ReleaseStatus }>) =>
    request<Release>(`/api/releases/${id}`, { method: "POST", body: JSON.stringify(payload) }),
  deleteRelease: (id: number) => request<void>(`/api/releases/${id}`, { method: "DELETE" }),

  analyzeReleaseNote: async (file: File): Promise<ReleaseNoteAnalyzeResponse> => {
    const formData = new FormData();
    formData.append("file", file);
    const response = await fetch(apiUrl("/api/releases/analyze-rn"), {
      method: "POST",
      body: formData,
      cache: "no-store",
    });
    const body = (await response.json().catch(() => ({}))) as ReleaseNoteAnalyzeResponse & ApiError;
    if (!response.ok) {
      throw new ApiRequestError(response.status, body?.detail ?? body?.message ?? "No se pudo analizar el Release Note.");
    }
    return body;
  },
  getReleaseAnalysis: (releaseId: number) =>
    request<ReleaseAnalysis>(`/api/releases/${releaseId}/analysis`),
  analyzeOperativaRn: async (file: File): Promise<OperativaAnalysisResult> => {
    const formData = new FormData();
    formData.append("file", file);
    const response = await fetch(apiUrl("/api/operativa/analyze-rn"), {
      method: "POST",
      body: formData,
      cache: "no-store",
    });
    const body = (await response.json().catch(() => ({}))) as OperativaAnalysisResult & ApiError;
    if (!response.ok) {
      throw new ApiRequestError(response.status, body?.detail ?? body?.message ?? "No se pudo analizar el RN Operativo.");
    }
    return body;
  },
  getOperativaRelease: (id: number) => request<OperativaReleaseRead>(`/api/operativa/${id}`),
  deleteOperativaRelease: (id: number) =>
    request<void>(`/api/operativa/${id}`, { method: "DELETE" }),
  listOperativaReleases: () => request<OperativaReleaseRead[]>("/api/operativa"),
  createReleaseFromOperativa: (operativaReleaseId: number) =>
    request<Release>(`/api/operativa/${operativaReleaseId}/create-release`, { method: "POST" }),
  listEpcsForQcRelease: (qcReleaseId: number) =>
    request<EpcRead[]>(`/api/operativa/qc-releases/${qcReleaseId}/epcs`),
  updateOperativaRelease: (id: number, payload: OperativaReleaseUpdate) =>
    request<OperativaReleaseRead>(`/api/operativa/${id}`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateEpc: (epcId: number, payload: EpcUpdate) =>
    request<EpcRead>(`/api/operativa/epcs/${epcId}`, { method: "POST", body: JSON.stringify(payload) }),
  createBeReleaseWithoutRn: () =>
    request<BeReleaseRead>("/api/releases-be", { method: "POST" }),
  listBeReleases: () => request<BeReleaseRead[]>("/api/releases-be"),
  getBeRelease: (id: number) => request<BeReleaseRead>(`/api/releases-be/${id}`),
  updateBeRelease: (id: number, payload: BeReleaseUpdate) =>
    request<BeReleaseRead>(`/api/releases-be/${id}`, { method: "POST", body: JSON.stringify(payload) }),
  analyzeBeRn: async (file: File): Promise<BeAnalysisResult> => {
    const formData = new FormData();
    formData.append("file", file);
    const response = await fetch(apiUrl("/api/releases-be/analyze-rn"), {
      method: "POST",
      body: formData,
      cache: "no-store",
    });
    const body = (await response.json().catch(() => ({}))) as BeAnalysisResult & ApiError;
    if (!response.ok) {
      throw new ApiRequestError(response.status, body?.detail ?? body?.message ?? "No se pudo analizar el RN de BE.");
    }
    return body;
  },
  createReleaseFromBe: (beReleaseId: number) =>
    request<Release>(`/api/releases-be/${beReleaseId}/create-release`, { method: "POST" }),
  generateCasesFromRN: (releaseId: number, regenerate = false) =>
    request<GenerateCasesResponse>(
      `/api/releases/${releaseId}/generate-cases${regenerate ? "?regenerate=true" : ""}`,
      {
        method: "POST",
      },
    ),
  getCoverageMatrix: (releaseId: number, brfKey?: string) => {
    const query = brfKey ? `?brf_key=${encodeURIComponent(brfKey)}` : "";
    return request<CoverageMatrixResponse>(`/api/releases/${releaseId}/coverage-matrix${query}`);
  },
  // QCO_ZEPHYR_PUBLISH — kept; UI hidden via SHOW_QCO_ZEPHYR_PUBLISH.
  publishOperativaToQco: (releaseId: number) =>
    request<PublishCasesResponse>(`/api/releases/${releaseId}/publish-qco`, { method: "POST" }),
  exportReleaseTestCases: async (releaseId: number, releaseName: string): Promise<void> => {
    let response: Response;
    try {
      response = await fetch(apiUrl(`/api/releases/${releaseId}/test-cases/export`), {
        cache: "no-store",
      });
    } catch {
      throw new ApiRequestError(503, "No se pudo contactar al servidor para exportar el Excel.");
    }
    const contentType = response.headers.get("content-type") ?? "";
    if (!response.ok) {
      const body = (await response.json().catch(() => ({}))) as { detail?: unknown; message?: string };
      const detail = typeof body.detail === "string" ? body.detail : body.message;
      throw new ApiRequestError(
        response.status,
        detail || "No se pudo exportar el Excel.",
      );
    }
    if (contentType.includes("application/json")) {
      const body = (await response.json().catch(() => ({}))) as { detail?: string; message?: string };
      throw new ApiRequestError(502, body.detail ?? body.message ?? "El servidor no devolvió un Excel.");
    }
    const blob = await response.blob();
    if (blob.size < 64) {
      throw new ApiRequestError(502, "El Excel exportado llegó vacío.");
    }
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const safe = releaseName.replace(/[<>:"/\\|?*]+/g, "_").replace(/\s+/g, "_").slice(0, 80) || "Release";
    link.href = url;
    link.download = `CaseForge_${safe}_TestCases.xlsx`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  },

  listTestCases: (releaseId: number) =>
    request<TestCase[]>(`/api/releases/${releaseId}/test-cases`),
  createTestCase: (releaseId: number, payload: TestCaseInput) =>
    request<TestCaseWithSteps>(`/api/releases/${releaseId}/test-cases`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getTestCase: (id: number) => request<TestCaseWithSteps>(`/api/test-cases/${id}`),
  updateTestCase: (id: number, payload: Partial<TestCaseInput> & { status?: TestCase["status"] }) =>
    request<TestCaseWithSteps>(`/api/test-cases/${id}`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  deleteTestCase: (id: number) => request<void>(`/api/test-cases/${id}`, { method: "DELETE" }),

  addStep: (testCaseId: number, payload: TestStepInput) =>
    request<TestStep>(`/api/test-cases/${testCaseId}/steps`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateStep: (stepId: number, payload: Partial<TestStepInput>) =>
    request<TestStep>(`/api/steps/${stepId}`, { method: "POST", body: JSON.stringify(payload) }),
  deleteStep: (stepId: number) => request<void>(`/api/steps/${stepId}`, { method: "DELETE" }),
  reorderSteps: (testCaseId: number, steps: { id: number; step_number: number }[]) =>
    request<TestStep[]>(`/api/test-cases/${testCaseId}/steps/reorder`, {
      method: "PUT",
      body: JSON.stringify({ steps }),
    }),

  getDashboardSummary: () => request<DashboardSummary>("/api/dashboard/summary"),

  // Bulk-import pipeline: Import -> Validate -> Preview happen here; Approve -> Persist reuses
  // bulkCreateTestCases below, which calls the exact same endpoint as any other bulk creation.
  listImportSheets: async (releaseId: number, file: File): Promise<ImportSheetsResult> => {
    const formData = new FormData();
    formData.append("file", file);
    const response = await fetch(apiUrl(`/api/releases/${releaseId}/test-cases/import/sheets`), {
      method: "POST",
      body: formData,
      cache: "no-store",
    });
    const body = (await response.json().catch(() => ({}))) as ImportSheetsResult & ApiError;
    if (!response.ok) {
      throw new ApiRequestError(response.status, body?.detail ?? body?.message ?? "No se pudo leer el archivo.");
    }
    return body;
  },
  previewImport: async (releaseId: number, file: File, sheetName?: string): Promise<ImportPreviewResult> => {
    const formData = new FormData();
    formData.append("file", file);
    if (sheetName) formData.append("sheet_name", sheetName);
    const response = await fetch(apiUrl(`/api/releases/${releaseId}/test-cases/import/preview`), {
      method: "POST",
      body: formData,
      cache: "no-store",
    });
    const body = (await response.json().catch(() => ({}))) as ImportPreviewResult & ApiError;
    if (!response.ok) {
      throw new ApiRequestError(response.status, body?.detail ?? body?.message ?? "No se pudo procesar el archivo.");
    }
    return body;
  },
  bulkCreateTestCases: (releaseId: number, testCases: ImportCandidateTestCase[]) =>
    request<BulkCreateResult>(`/api/releases/${releaseId}/test-cases/bulk`, {
      method: "POST",
      body: JSON.stringify({ test_cases: testCases }),
    }),

  getQcSummary: (filters?: QcSummaryFilters) => {
    const query = new URLSearchParams();
    if (filters?.month) query.set("month", filters.month);
    if (filters?.release_id) query.set("release_id", String(filters.release_id));
    if (filters?.operational_window_id) query.set("operational_window_id", String(filters.operational_window_id));
    if (filters?.release_window_id) query.set("release_window_id", String(filters.release_window_id));
    if (filters?.cluster) query.set("cluster", filters.cluster);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return request<QcDashboardSummary>(`/api/dashboard/qc-summary${suffix}`);
  },
  getReleaseKpis: () => request<ReleaseKpisRead>("/api/kpis/releases"),
  getCalendarDay: (date?: string) => {
    const suffix = date ? `?date=${encodeURIComponent(date)}` : "";
    return request<QcCalendarDayResponse>(`/api/calendar/day${suffix}`);
  },
  getCalendarWeek: (date?: string) => {
    const suffix = date ? `?date=${encodeURIComponent(date)}` : "";
    return request<QcCalendarWeekResponse>(`/api/calendar/week${suffix}`);
  },
  uploadCalendarIcs: async (file: File): Promise<{ status: string; bytes: number }> => {
    const formData = new FormData();
    formData.append("file", file);
    const response = await fetch(apiUrl("/api/calendar/ics"), { method: "POST", body: formData, cache: "no-store" });
    const body = (await response.json().catch(() => ({}))) as { status?: string; bytes?: number; detail?: string; message?: string };
    if (!response.ok) {
      const raw = body.detail ?? body.message ?? "No se pudo cargar el .ics";
      throw new ApiRequestError(response.status, typeof raw === "string" ? raw : JSON.stringify(raw));
    }
    return { status: body.status || "ok", bytes: body.bytes || 0 };
  },
  listOperationalWindows: () => request<OperationalWindow[]>("/api/operational-windows"),
  listAllReleaseWindows: () => request<ReleaseWindow[]>("/api/release-windows"),
  createReleaseWindow: (
    releaseId: number,
    payload: { name: string; start_date: string; end_date: string; status?: "PLANNED" | "ACTIVE" | "CLOSED" },
  ) => request<ReleaseWindow>(`/api/releases/${releaseId}/windows`, { method: "POST", body: JSON.stringify(payload) }),

  // QcTicket: independent defect radar (Import -> Validate -> Preview -> Approve -> Persist).
  previewQcTicketImport: async (
    file: File, view: QcTicketView, source: QcTicketSource
  ): Promise<QcTicketImportPreviewResult> => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("view", view);
    formData.append("source", source);
    const response = await fetch(apiUrl("/api/qc-tickets/import/preview"), {
      method: "POST",
      body: formData,
      cache: "no-store",
    });
    const body = (await response.json().catch(() => ({}))) as QcTicketImportPreviewResult & ApiError;
    if (!response.ok) {
      throw new ApiRequestError(response.status, body?.detail ?? body?.message ?? "No se pudo procesar el archivo.");
    }
    return body;
  },
  bulkCreateQcTickets: (tickets: QcTicketCreate[]) =>
    request<QcTicketBulkCreateResult>("/api/qc-tickets/bulk", { method: "POST", body: JSON.stringify(tickets) }),
  getQcTicketStats: (view: QcTicketView, cluster?: string, bugType?: "QC" | "QA") => {
    const params = new URLSearchParams({ view });
    if (cluster) params.set("cluster", cluster);
    if (bugType) params.set("bug_type", bugType);
    return request<QcTicketStats>(`/api/qc-tickets/stats?${params.toString()}`);
  },
  refreshQcTicketsFromJira: (view: QcTicketView) =>
    request<QcTicketJiraRefreshResult>(`/api/qc-tickets/jira/refresh?view=${encodeURIComponent(view)}`, {
      method: "POST",
    }),
  listQcTickets: (view: QcTicketView, bugType?: "QC" | "QA") => {
    const params = new URLSearchParams({ view });
    if (bugType) params.set("bug_type", bugType);
    return request<QcTicketRead[]>(`/api/qc-tickets?${params.toString()}`);
  },
  getQcRadarConfig: () => request<QcRadarConfigResponse>("/api/qc-tickets/filters"),

  // Deliverable: read-focused (creation is implicit via get-or-create in createRelease above).
  listDeliverables: (name?: string) => {
    const suffix = name ? `?name=${encodeURIComponent(name)}` : "";
    return request<Deliverable[]>(`/api/deliverables${suffix}`);
  },
  getDeliverable: (id: number) => request<DeliverableWithMetrics>(`/api/deliverables/${id}`),
  listDeliverableReleases: (id: number) =>
    request<DeliverableReleaseSummary[]>(`/api/deliverables/${id}/releases`),
};
