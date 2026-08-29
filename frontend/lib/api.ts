import type {
  ApiError,
  BulkCreateResult,
  DashboardSummary,
  ImportCandidateTestCase,
  ImportPreviewResult,
  ImportSheetsResult,
  OperationalWindow,
  QcDashboardSummary,
  QcSummaryFilters,
  QcTicketBulkCreateResult,
  QcTicketCreate,
  QcTicketImportPreviewResult,
  QcTicketSource,
  QcTicketStats,
  QcTicketView,
  Release,
  ReleaseStatus,
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    cache: "no-store",
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const body = (await response.json().catch(() => ({}))) as T & ApiError;

  if (!response.ok) {
    const message = body?.detail ?? body?.message ?? `Request failed (${response.status})`;
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
  listReleases: (params?: { status?: ReleaseStatus; platform?: string }) => {
    const query = new URLSearchParams();
    if (params?.status) query.set("status", params.status);
    if (params?.platform) query.set("platform", params.platform);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return request<ReleaseWithCounts[]>(`/api/releases${suffix}`);
  },
  createRelease: (payload: ReleaseInput) =>
    request<Release>("/api/releases", { method: "POST", body: JSON.stringify(payload) }),
  getRelease: (id: number) => request<Release>(`/api/releases/${id}`),
  updateRelease: (id: number, payload: Partial<ReleaseInput & { status: ReleaseStatus }>) =>
    request<Release>(`/api/releases/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteRelease: (id: number) => request<void>(`/api/releases/${id}`, { method: "DELETE" }),

  analyzeReleaseNote: async (file: File): Promise<ReleaseNoteAnalyzeResponse> => {
    const formData = new FormData();
    formData.append("file", file);
    const response = await fetch("/api/releases/analyze-rn", {
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
  generateCasesFromRN: (releaseId: number) =>
    request<{ status: string; message: string; release_id: number }>(`/api/releases/${releaseId}/generate-cases`, {
      method: "POST",
    }),

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
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteTestCase: (id: number) => request<void>(`/api/test-cases/${id}`, { method: "DELETE" }),

  addStep: (testCaseId: number, payload: TestStepInput) =>
    request<TestStep>(`/api/test-cases/${testCaseId}/steps`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateStep: (stepId: number, payload: Partial<TestStepInput>) =>
    request<TestStep>(`/api/steps/${stepId}`, { method: "PATCH", body: JSON.stringify(payload) }),
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
    const response = await fetch(`/api/releases/${releaseId}/test-cases/import/sheets`, {
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
    const response = await fetch(`/api/releases/${releaseId}/test-cases/import/preview`, {
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
    const response = await fetch("/api/qc-tickets/import/preview", {
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
  getQcTicketStats: (view: QcTicketView, cluster?: string) => {
    const params = new URLSearchParams({ view });
    if (cluster) params.set("cluster", cluster);
    return request<QcTicketStats>(`/api/qc-tickets/stats?${params.toString()}`);
  },
  getQcRadarConfig: () => request<QcRadarConfigResponse>("/api/qc-tickets/filters"),
};
