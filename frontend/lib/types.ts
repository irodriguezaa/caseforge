export type ReleaseStatus = "DRAFT" | "IN_PROGRESS" | "COMPLETED" | "CANCELLED";
export type ReleaseType = "NUEVO" | "REVALIDACION";
export type AuthRole = "jefe" | "lider" | "tester" | "consulta";

export interface AuthUser {
  email: string;
  role: AuthRole;
}

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
  tri_issues_count: number;
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

export interface GeneratedCaseStep {
  step_number: number;
  action: string;
  expected_result: string;
  test_data?: string | null;
}

export interface GeneratedCaseCandidate {
  name: string;
  description: string;
  precondition: string | null;
  requires_condition: boolean;
  steps: GeneratedCaseStep[];
  test_data?: string | null;
  related_functionality: string | null;
  related_jira: string | null;
  related_rn: string | null;
  evidence: string;
  justification: string;
  possible_duplicate_of: string | null;
  confidence: "high" | "medium" | "low";
  review_required: boolean;
  basic_validation?: boolean;
  priority?: "BLOCKER" | "CRITICAL" | null;
  priority_reason?: string | null;
  user_type?: string | null;
  use_case_key?: string | null;
  use_case_title?: string | null;
  access_path?: string | null;
  device?: string | null;
  country?: string | null;
  device_source?: string | null;
  mdp?: string | null;
  behavior?: string | null;
  hn_keys?: string[];
  candidate_id?: string | null;
  duplicate_status?: "UNIQUE" | "POSSIBLE_DUPLICATE" | "OVERLAP" | null;
  duplicate_with?: string[];
  ecosystem?: string | null;
  applicability_reason?: string | null;
  group_id?: string | null;
  interaction_points?: string[];
  hn_source?: string | null;
}

export interface GenerateCasesResponse {
  status: string;
  message: string;
  release_id: number;
  release_name: string;
  validation_type: string | null;
  has_analysis: boolean;
  engine: string;
  candidates: GeneratedCaseCandidate[];
  persisted: boolean;
  already_generated?: boolean;
  test_case_count?: number;
  estimation_hours?: number;
  estimation_days?: number;
  analysis_details?: string[];
  brfs_analyzed?: number;
  device_review_count?: number;
  possible_duplicate_count?: number;
}

export interface PublishCasesResponse {
  status: string;
  message: string;
  release_id: number;
  sent: number;
  created: number;
  errors: number;
  duplicates: number;
  rejected: number;
  caseforge_unmodified: boolean;
  records: Array<{
    caseforge_id: string;
    zephyr_id: string | null;
    brf: string;
    hn: string;
    device_channel: string;
    name: string;
    steps: number;
    status: string;
    resultado: string;
    detail: string;
  }>;
}

export interface CoverageMatrixRow {
  brf_key: string;
  epc_keys: string[];
  hn_keys: string[];
  behavior_key: string;
  behavior_title: string;
  interaction_points: string[];
  channel: string | null;
  ecosystem: string | null;
  applicable_devices: string[];
  relevant_users: string[];
  mdp: string[];
  test_data: string | null;
  origin: string;
  evidence: string;
  applicability_reason: string;
  duplicate_risk: string;
  duplicate_with: string[];
  rules: string[];
}

export interface CoverageMatrixResponse {
  status: string;
  engine: string;
  release_id: number;
  release_name: string;
  brfs_analyzed: number;
  row_count: number;
  rows: CoverageMatrixRow[];
  notes: string[];
  hn_source_by_brf: Record<string, string>;
  hn_coverage?: Array<{
    brf_key: string;
    hn_key: string;
    status: string;
    disposition?: string | null;
    related_hn?: string[];
    behavior_keys: string[];
    reason: string;
  }>;
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
  deliverable_id: number | null;
  release_type: ReleaseType | null;
  parent_release_id: number | null;
  parent_release_name?: string | null;
  operativa_release_id: number | null;
  be_release_id: number | null;
  deliverable_name?: string | null;
  swf?: string | null;
  regresivo_scope?: "COMPLETO" | "SMOKE" | "ACOTADO" | null;
  affected_component?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReleaseWithCounts extends Release {
  test_case_count: number;
  latest_analysis?: ReleaseAnalysis | null;
  deliverable_name: string | null;
}

export interface Deliverable {
  id: number;
  name: string;
  created_at: string;
  updated_at: string;
}

export interface DeliverableReleaseSummary {
  id: number;
  name: string;
  version: string;
  status: ReleaseStatus;
  release_type: ReleaseType | null;
  parent_release_id: number | null;
  deliverable_id?: number | null;
  created_at: string;
}

export interface DeliverableWithMetrics extends Deliverable {
  total_versions: number;
  total_evolutivas: number;
  total_revalidaciones: number;
  total_defects: number;
  latest_release_id: number | null;
  latest_release_status: ReleaseStatus | null;
  releases: DeliverableReleaseSummary[];
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
  test_data?: string | null;
  requires_condition?: boolean;
  evidence?: string | null;
  justification?: string | null;
  technical_epic?: string | null;
  technical_story?: string | null;
  scenario_origin?: string | null;
  related_rn?: string | null;
  confidence?: string | null;
  complexity?: string | null;
  estimation_hours?: number | null;
  generated_by_engine?: boolean;
  ecosystem?: string | null;
  device?: string | null;
  device_source?: string | null;
  applicability_reason?: string | null;
  duplicate_status?: string | null;
  group_id?: string | null;
  hn_source?: string | null;
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
  deliverable_name: string | null;
  release_type: ReleaseType | null;
  deliverable_release_ordinal: number | null;
  deliverable_total_versions: number | null;
  deliverable_total_revalidaciones: number | null;
  origin_kind: "APP" | "BE" | "OPERATIVA";
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
  execution_items: ActivityItem[];
  in_progress_app: number;
  in_progress_be: number;
  in_progress_operativa: number;
  in_progress_total: number;
}

export interface ClusterParticipation {
  cluster: string;
  count: number;
}

export interface DeliverableReleaseKpi {
  deliverable_id: number | null;
  deliverable_name: string;
  releases: number;
  versions: number | null;
}

export interface SwfReleaseKpi {
  swf: string;
  releases: number;
  percent: number;
}

export interface UnclassifiedSwfKpi {
  origin: string;
  platform: string | null;
  count: number;
  reason: string;
}

export interface SwfDistributionKpi {
  considered: number;
  unclassified: number;
  by_swf: SwfReleaseKpi[];
  unclassified_rows: UnclassifiedSwfKpi[];
}

export interface RevalidationKpi {
  total: number;
  app: number;
  nuevo: number;
  revalidacion: number;
  untyped_app: number;
  revalidacion_percent: number;
  scope: string;
}

export interface ReleaseKpisRead {
  total: number;
  app: number;
  be: number;
  operativa: number;
  by_month: ReleaseVolumeMonth[];
  by_cluster: ClusterParticipation[];
  cluster_validations_total: number;
  clusters_per_release_avg: number;
  by_deliverable: DeliverableReleaseKpi[];
  swf: SwfDistributionKpi;
  revalidation: RevalidationKpi;
}

export interface ReleaseVolumeMonth {
  month: string;
  total: number;
  app: number;
  be: number;
  operativa: number;
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

export interface QcTicketJiraRefreshFilterResult {
  filter_id: string;
  source: string;
  jira_count: number;
  mapped: number;
  skipped: number;
}

export interface QcTicketJiraRefreshResult {
  created: number;
  updated: number;
  skipped: number;
  filter_ids: string[];
  filters: QcTicketJiraRefreshFilterResult[];
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
  by_month_priority: Record<string, { BLOCKER: number; CRITICAL: number; OTHER: number }>;
  open_by_priority: Record<string, number>;
  by_status: Record<string, number>;
  by_device: Record<string, number>;
  by_program: Record<string, number>;
  by_quarter: Record<string, number>;
  severity_by_swf: Record<string, { BLOCKER: number; CRITICAL: number; OTHER: number }>;
  swf_by_month: Record<string, Record<string, number>>;
  leak_by_month: Record<string, { leaked: number; rate: number }>;
  leak_by_swf: Record<string, number>;
  leak_by_project: Record<string, number>;
}

export interface QcTicketRead {
  id: number;
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
  imported_at: string;
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

export interface EpcRead {
  id: number;
  operativa_release_id: number;
  release_id?: number | null;
  brf_key: string;
  epc_key: string | null;
  titulo: string;
  alcance: string | null;
  nota_rte: string | null;
  estado_jira: string | null;
  qc_suggestion: "SUGERIDO_INCLUIR" | "SUGERIDO_EXCLUIR" | "REQUIERE_REVISION";
  include_in_qc: boolean;
  alcance_funcional: string | null;
  dispositivos_aplicables: string[] | null;
}

export interface OperativaReleaseRead {
  id: number;
  name: string | null;
  entregable: string | null;
  cluster: string | null;
  description: string | null;
  pdf_filename: string;
  start_date: string | null;
  end_date: string | null;
  jira_filter_url: string | null;
  jira_filter_manual: string | null;
  instrucciones_adicionales: string | null;
  epcs: EpcRead[];
  qc_release_id?: number | null;
  qc_release_status?: string | null;
}

export interface OperativaReleaseUpdate {
  name?: string | null;
  entregable?: string | null;
  cluster?: string | null;
  description?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  jira_filter_url?: string | null;
  jira_filter_manual?: string | null;
  instrucciones_adicionales?: string | null;
}

export interface OperativaAnalysisResult {
  operativa_release: OperativaReleaseRead;
}

export interface EpcUpdate {
  include_in_qc?: boolean;
  alcance_funcional?: string;
  dispositivos_aplicables?: string[];
}

export type BeRegresivoScope = "COMPLETO" | "SMOKE" | "ACOTADO";
export type BeSwf = "BE Hitss" | "BE Nubiral" | "BE Neoris";

export type BeCluster = "Todos" | "Global" | "AUP" | "CENAM" | "Andina" | "Dominicana";

export interface BeReleaseRead {
  id: number;
  name: string | null;
  entregable: string | null;
  swf: string | null;
  clusters: string[] | null;
  description: string | null;
  pdf_filename: string | null;
  regresivo_scope: BeRegresivoScope | null;
  affected_component: string | null;
  start_date: string | null;
  end_date: string | null;
  qc_release_id?: number | null;
  qc_release_status?: string | null;
}

export interface BeReleaseUpdate {
  name?: string | null;
  entregable?: string | null;
  swf?: BeSwf | null;
  clusters?: BeCluster[] | null;
  description?: string | null;
  regresivo_scope?: BeRegresivoScope | null;
  affected_component?: string | null;
  start_date?: string | null;
  end_date?: string | null;
}

export interface BeAnalysisResult {
  be_release: BeReleaseRead;
}

export interface QcCalendarEvent {
  id: string;
  title: string;
  start: string;
  end: string;
  location?: string | null;
  is_live: boolean;
  web_link?: string | null;
  categories: string[];
  source?: string;
}

export interface QcCalendarDayResponse {
  date: string;
  events: QcCalendarEvent[];
  feed?: string;
  outlook_note?: string | null;
}

export interface QcCalendarWeekResponse {
  week_start: string;
  events: QcCalendarEvent[];
  feed?: string;
  outlook_note?: string | null;
}
