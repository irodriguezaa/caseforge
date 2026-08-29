export type ReleaseStatus = "DRAFT" | "IN_PROGRESS" | "COMPLETED" | "CANCELLED";

export type TestCasePriority = "BLOCKER" | "CRITICAL";

export interface ImportCandidateTestCase {
  test_case_id: string;
  component: string;
  test_case_name: string;
  description: string | null;
  user_type: string | null;
  priority: TestCasePriority;
  test_type: TestCaseType;
  status: TestCaseStatus;
  steps: { step_number: number; test_step: string; expected_result: string }[];
}

export interface ImportRowError {
  test_case_id: string | null;
  row_numbers: number[];
  message: string;
}

export interface ImportPreviewResult {
  valid: ImportCandidateTestCase[];
  errors: ImportRowError[];
  warnings: ImportRowError[];
  format: "FLAT" | "EMBEDDED";
  sheet_name: string;
  total_rows: number;
  total_test_cases: number;
  valid_count: number;
  error_count: number;
}

export interface ImportSheetInfo {
  name: string;
  format: "FLAT" | "EMBEDDED" | "UNKNOWN";
}

export interface ImportSheetsResult {
  sheets: ImportSheetInfo[];
  recommended_sheet: string | null;
}

export interface BulkCreateError {
  index: number;
  test_case_id: string | null;
  message: string;
}

export interface BulkCreateResult {
  created: TestCaseWithSteps[];
  errors: BulkCreateError[];
}
export type TestCaseType = "FUNCTIONAL" | "REGRESSION" | "SMOKE" | "UI" | "PERFORMANCE" | "OTHER";
export type TestCaseStatus = "UNEXECUTED" | "PASS" | "FAIL" | "BLOCKED" | "N_A";

export interface ReleaseAnalysis {
  id?: number;
  release_id?: number | null;
  pdf_filename: string;
  pdf_file_path?: string | null;
  detected_name?: string | null;
  detected_version?: string | null;
  detected_platform?: string | null;
  detected_description?: string | null;
  features_count: number;
  qa_qc_issues_count: number;
  nco_issues_count: number;
  detected_devices?: string | null;
  proposed_coverage?: number | null;
  estimation_text?: string | null;
  observations: string[];
  raw_analysis?: Record<string, unknown>;
  qc_engine_version: string;
  created_at?: string;
  updated_at?: string;
}

export interface ReleaseNoteAnalyzeResponse {
  analysis: ReleaseAnalysis;
  calculated_business_days: number;
}

export interface Release {
  id: number;
  name: string;
  version: string;
  description: string | null;
  platform: string;
  cluster: string | null;
  status: ReleaseStatus;
  start_date?: string | null;
  end_date?: string | null;
  qc_resources?: number | null;
  execution_days?: number | null;
  validation_type?: string | null;
  jira_issue_filter?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReleaseWithCounts extends Release {
  test_case_count: number;
  latest_analysis?: ReleaseAnalysis | null;
}

export interface TestStep {
  id: number;
  test_case_id: number;
  step_number: number;
  test_step: string;
  expected_result: string;
  created_at: string;
  updated_at: string;
}

export interface TestCase {
  id: number;
  release_id: number;
  test_case_id: string;
  component: string;
  test_case_name: string;
  description: string | null;
  user_type: string | null;
  priority: TestCasePriority;
  test_type: TestCaseType;
  status: TestCaseStatus;
  created_at: string;
  updated_at: string;
}

export interface TestCaseWithSteps extends TestCase {
  steps: TestStep[];
}

export interface DashboardSummary {
  releases_total: number;
  releases_by_status: Partial<Record<ReleaseStatus, number>>;
  test_cases_total: number;
  test_cases_by_status: Partial<Record<TestCaseStatus, number>>;
  test_cases_by_priority: Partial<Record<TestCasePriority, number>>;
}

export type WindowStatus = "PLANNED" | "ACTIVE" | "CLOSED";

export interface OperationalWindow {
  id: number;
  name: string;
  start_date: string;
  end_date: string;
  cluster: string | null;
  status: WindowStatus;
  created_at: string;
  updated_at: string;
}

export interface ReleaseWindow {
  id: number;
  release_id: number;
  name: string;
  start_date: string;
  end_date: string;
  status: WindowStatus;
  created_at: string;
  updated_at: string;
}

export type RiskLevel = "LOW" | "MEDIUM" | "HIGH";

export interface AtRiskItem {
  type: "operational_window" | "release_window";
  id: number;
  name: string;
  reasons: string[];
}

export interface ActivityItem {
  release_id: number;
  release_name: string;
  release_version: string;
  platform: string;
  cluster: string | null;
  window_name: string | null;
  window_start_date: string | null;
  window_end_date: string | null;
  status: ReleaseStatus;
  planned: number;
  executed: number;
  pass_count: number;
  fail_count: number;
  blocked_count: number;
  unexecuted_count: number;
  defects_blocker_count: number;
  percent_avance: number;
  percent_cobertura: number;
  risk_level: RiskLevel;
  risk_reasons: string[];
}

export interface QcDashboardSummary {
  windows_total: number;
  windows_active: number;
  operational_windows_total: number;
  operational_windows_active: number;
  release_windows_total: number;
  release_windows_active: number;
  releases_open: number;
  test_cases_planned: number;
  test_cases_executed: number;
  percent_avance: number;
  percent_cobertura: number;
  pass_count: number;
  fail_count: number;
  blocked_count: number;
  unexecuted_count: number;
  defects_found: number;
  defects_critical: number;
  at_risk: AtRiskItem[];
  active_items: ActivityItem[];
}

export interface QcSummaryFilters {
  month?: string;
  release_id?: number;
  operational_window_id?: number;
  release_window_id?: number;
  cluster?: string;
}

export interface ApiError {
  detail?: string;
  message?: string;
}

export type QcTicketPriority = "BLOCKER" | "CRITICAL" | "OTHER";
export type QcTicketSource = "QC_DETECTED" | "LEAKED";
export type QcTicketView = "OPERATIVAS" | "RELEASE";

export interface QcTicketCreate {
  issue_key: string;
  issue_type: string | null;
  project_key: string | null;
  priority_bucket: QcTicketPriority;
  status_raw: string;
  is_open: boolean;
  view: QcTicketView;
  source: QcTicketSource;
  cluster: string | null;
  affected_program: string | null;
  device: string | null;
  swf: string | null;
  is_attributed: boolean | null;
  created_date: string;
  resolved_date: string | null;
  summary: string | null;
}

export interface QcTicketImportRowError {
  issue_key: string | null;
  row_number: number | null;
  message: string;
}

export interface QcTicketImportPreviewResult {
  valid: QcTicketCreate[];
  errors: QcTicketImportRowError[];
  warnings: QcTicketImportRowError[];
  total_rows: number;
  excluded_cancelled_count: number;
  valid_count: number;
  error_count: number;
}

export interface QcTicketBulkCreateResult {
  created: (QcTicketCreate & { id: number; imported_at: string })[];
  errors: { issue_key: string | null; message: string }[];
}

export interface QcTicketStats {
  total: number;
  blocker_count: number;
  critical_count: number;
  other_count: number;
  open_count: number;
  qc_detected_count: number;
  leaked_count: number;
  leak_rate_percent: number;
  genuine_leak_count: number | null;
  by_cluster: Record<string, number>;
  by_swf: Record<string, number>;
  by_month: Record<string, number>;
}

export interface QcRadarFilterItem {
  filter_id: string;
  label: string;
  description: string;
  tag: string;
}

export interface QcRadarViewConfig {
  detected: QcRadarFilterItem;
  leaked: QcRadarFilterItem;
}

export interface QcRadarConfigResponse {
  OPERATIVAS: QcRadarViewConfig;
  RELEASE: QcRadarViewConfig;
}
