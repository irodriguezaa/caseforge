"use client";

import { Download, Pencil, Plus, Sparkles, Trash2, Upload } from "lucide-react";
import { ColumnFilter } from "@/app/components/ColumnFilter";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { EditTestCaseModal } from "@/app/components/EditTestCaseModal";
import { TestCaseBulkBar } from "@/app/components/TestCaseBulkBar";
import { EpicHoursPanel } from "@/app/components/EpicHoursPanel";
import { EpicProgressPanel } from "@/app/components/EpicProgressPanel";
import { ImportTestCasesPanel } from "@/app/components/ImportTestCasesPanel";
import { InfoTooltip } from "@/app/components/InfoTooltip";
import { OperativaCoverageMatrix } from "@/app/components/OperativaCoverageMatrix";
import { OperativaEpcTable } from "@/app/components/OperativaEpcTable";
import { ReleaseAnalysisCard } from "@/app/components/ReleaseAnalysisCard";
import { StatusBadge } from "@/app/components/StatusBadge";
import { api, ApiRequestError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  columnFilterIsActive,
  loadReleaseCaseFilters,
  pruneFilterList,
  saveReleaseCaseFilters,
  type ColumnFilterSelection,
} from "@/lib/releaseCaseFilters";
import {
  componentLabel,
  filterReleaseCases,
  headerCheckboxState,
  selectFilteredIds,
  storyLabel,
  summarizeBulkResult,
  toggleSelectedId,
} from "@/lib/releaseCaseSelection";
import { MatrixScopeEditor } from "@/app/components/MatrixScopeEditor";
import { ValidationScopeSelect, ValidationScopeSummary } from "@/app/components/ValidationScopeField";
import { OPERATIVA_DEVICE_OPTIONS, SHOW_QCO_ZEPHYR_PUBLISH } from "@/lib/constants";
import { calculateBusinessDays } from "@/lib/dateUtils";
import { nextTestCaseId } from "@/lib/testCaseId";
import { QC_ESTIMATION_TOOLTIP, QC_HOURS_PER_DAY, QC_OPERATIVA_ESTIMATION_TOOLTIP, durationDays, estimateOperativaEffort, estimateReleaseEffortFromCases, estimateReleaseEffortLegacyCount, hoursByTechnicalEpic, progressByTechnicalEpic, rnScopeCoverage, rnScopeEpicKeys, stripDeviceFromCaseName } from "@/lib/qcEffort";
import { validationScopeHours } from "@/lib/validationScope";
import type { CoverageMatrixResponse, EpcRead, GenerateCasesResponse, PublishCasesResponse, Release, ReleaseAnalysis, ReleaseStatus, TestCase } from "@/lib/types";
import { JiraFilterLink } from "@/app/components/JiraFilterLink";
import { jiraIssueUrl, parseJiraFilterId, parseJiraTicketKeys } from "@/lib/jira";
import { formatRnSourceType } from "@/lib/types";

const emptyForm = {
  test_case_id: "",
  component: "",
  test_case_name: "",
  device: "",
  priority: "CRITICAL" as TestCase["priority"],
  test_type: "FUNCTIONAL" as TestCase["test_type"],
};

const NEXT_STATUS: Partial<Record<ReleaseStatus, ReleaseStatus[]>> = {
  DRAFT: ["IN_PROGRESS", "CANCELLED"],
  IN_PROGRESS: ["DRAFT", "COMPLETED", "CANCELLED"],
};

function formatDate(isoDate?: string | null): string {
  if (!isoDate) return "—";
  const [y, m, d] = isoDate.slice(0, 10).split("-");
  if (!y || !m || !d) return "—";
  return `${d}/${m}/${y}`;
}

function toDateInputValue(isoDate?: string | null): string {
  if (!isoDate) return "";
  const day = isoDate.slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(day) ? day : "";
}

function uniqueSorted(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b, "es"));
}

export default function ReleaseDetailPage(): React.ReactElement {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const releaseId = Number(params.id);
  const { canChangeReleaseStatus, canDeleteRelease, canLoadRn, canExecuteCases } = useAuth();

  const [release, setRelease] = useState<Release | null>(null);
  const [analysis, setAnalysis] = useState<ReleaseAnalysis | null>(null);
  const [includedEpcs, setIncludedEpcs] = useState<EpcRead[]>([]);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [submitting, setSubmitting] = useState(false);

  const [deviceFilter, setDeviceFilter] = useState<string>("");
  const [componentFilter, setComponentFilter] = useState<ColumnFilterSelection>(null);
  const [storyFilter, setStoryFilter] = useState<ColumnFilterSelection>(null);
  const [priorityFilter, setPriorityFilter] = useState<ColumnFilterSelection>(null);
  const [statusFilter, setStatusFilter] = useState<ColumnFilterSelection>(null);
  const skipFilterPersist = useRef(true);
  const [showImport, setShowImport] = useState(false);
  const [showManualForm, setShowManualForm] = useState(false);
  const [generateResult, setGenerateResult] = useState<GenerateCasesResponse | null>(null);
  const [coverageMatrix, setCoverageMatrix] = useState<CoverageMatrixResponse | null>(null);
  const [showAnalysisDetails, setShowAnalysisDetails] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [publishResult, setPublishResult] = useState<PublishCasesResponse | null>(null);
  const [exporting, setExporting] = useState(false);
  const [editingCase, setEditingCase] = useState<TestCase | null>(null);
  const [statusBusy, setStatusBusy] = useState(false);
  const [caseTab, setCaseTab] = useState<"rn" | "matrix">("rn");
  const [editingPlanning, setEditingPlanning] = useState(false);
  const [planningBusy, setPlanningBusy] = useState(false);
  const [planningForm, setPlanningForm] = useState({
    startDate: "",
    endDate: "",
    qcResources: 1,
    validationType: "",
    jiraIssueFilter: "",
    description: "",
  });
  const [matrixImpact, setMatrixImpact] = useState<{ caseCount: number; note: string; estimateInSection: boolean } | null>(null);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkNotice, setBulkNotice] = useState<{ ok: boolean; text: string } | null>(null);
  const headerSelectRef = useRef<HTMLInputElement>(null);

  const load = (): void => {
    setLoadError(null);
    Promise.all([api.getRelease(releaseId), api.listTestCases(releaseId)])
      .then(([releaseData, testCaseData]) => {
        setRelease(releaseData);
        setTestCases(testCaseData);
        if (releaseData.be_release_id) {
          setAnalysis(null);
          setIncludedEpcs([]);
          return;
        }
        if (releaseData.operativa_release_id) {
          setAnalysis(null);
          return Promise.all([
            api.listEpcsForQcRelease(releaseId).then(setIncludedEpcs),
            api.getCoverageMatrix(releaseId).then(setCoverageMatrix).catch(() => setCoverageMatrix(null)),
          ]).then(() => undefined);
        }
        setIncludedEpcs([]);
        return api.getReleaseAnalysis(releaseId).catch(() => null).then(setAnalysis);
      })
      .catch((err: unknown) => setLoadError(err instanceof Error ? err.message : "Error"));
  };

  useEffect(load, [releaseId]);

  const handleStatusChange = async (status: ReleaseStatus): Promise<void> => {
    if (!release) return;
    const previous = release;
    setActionError(null);
    setStatusBusy(true);
    setRelease({ ...release, status });
    try {
      const updated = await api.updateRelease(releaseId, { status });
      setRelease(updated);
    } catch (err) {
      setRelease(previous);
      setActionError(err instanceof ApiRequestError ? err.message : "No se pudo actualizar el estado.");
    } finally {
      setStatusBusy(false);
    }
  };

  const beginEditPlanning = (): void => {
    if (!release) return;
    setPlanningForm({
      startDate: toDateInputValue(release.start_date),
      endDate: toDateInputValue(release.end_date),
      qcResources: release.qc_resources ?? 1,
      validationType: release.validation_type ?? "",
      jiraIssueFilter: release.jira_issue_filter ?? "",
      description: release.description ?? "",
    });
    setEditingPlanning(true);
    setActionError(null);
  };

  const savePlanning = async (): Promise<void> => {
    if (planningForm.startDate && planningForm.endDate && planningForm.startDate > planningForm.endDate) {
      setActionError("La fecha de fin debe ser posterior o igual a la de inicio.");
      return;
    }
    setPlanningBusy(true);
    setActionError(null);
    try {
      const updated = await api.updateRelease(releaseId, {
        start_date: planningForm.startDate || null,
        end_date: planningForm.endDate || null,
        qc_resources: Math.max(1, Number(planningForm.qcResources) || 1),
        validation_type: planningForm.validationType.trim() || null,
        jira_issue_filter: planningForm.jiraIssueFilter.trim() || null,
        description: planningForm.description.trim() || null,
      });
      setRelease(updated);
      setEditingPlanning(false);
    } catch (err) {
      setActionError(err instanceof ApiRequestError ? err.message : "No se pudo guardar la planificación.");
    } finally {
      setPlanningBusy(false);
    }
  };

  const handleDelete = async (): Promise<void> => {
    setActionError(null);
    const confirmed = window.confirm(
      "Se eliminará la Release y su Release Note. Esta acción no se puede deshacer."
    );
    if (!confirmed) {
      return;
    }
    const destination = release?.operativa_release_id
      ? "/operativas/release-notes"
      : release?.be_release_id
        ? "/releases-be"
        : "/releases";
    try {
      await api.deleteRelease(releaseId);
      router.push(destination);
    } catch (err) {
      setActionError(err instanceof ApiRequestError ? err.message : "No se pudo eliminar la release.");
    }
  };

  const handleGenerateCases = async (regenerate = false): Promise<void> => {
    setActionError(null);
    setGenerateResult(null);
    setShowAnalysisDetails(false);
    if (release?.be_release_id) {
      setGenerateResult({
        status: "INFO",
        message: "Flujo de generación desde Matriz QC preparado. Completo, Smoke o Acotado se conectarán en la siguiente fase.",
        release_id: releaseId,
        release_name: release.name,
        validation_type: release.validation_type ?? null,
        has_analysis: false,
        engine: "be",
        candidates: [],
        persisted: false,
      });
      return;
    }
    const hasEngineCases = testCases.some((row) => row.generated_by_engine);
    if (regenerate && hasEngineCases) {
      const confirmed = window.confirm(
        "Esto reemplaza los Test Cases generados por el motor. Los casos importados o creados a mano se conservan. ¿Continuar?"
      );
      if (!confirmed) {
        return;
      }
    }
    setGenerating(true);
    try {
      const res = await api.generateCasesFromRN(releaseId, regenerate, (progress) => {
        setGenerateResult(progress);
      });
      setGenerateResult(res);
      load();
    } catch (err) {
      setActionError(err instanceof ApiRequestError ? err.message : "No se pudo generar los Test Cases.");
    } finally {
      setGenerating(false);
    }
  };

  const handlePublishQco = async (): Promise<void> => {
    setActionError(null);
    setPublishResult(null);
    const confirmed = window.confirm(
      "Esto publica los Test Cases del motor a Jira QCO (issuetype Test). No modifica los casos en QC Pulse. ¿Continuar?"
    );
    if (!confirmed) {
      return;
    }
    setPublishing(true);
    try {
      const res = await api.publishOperativaToQco(releaseId);
      setPublishResult(res);
    } catch (err) {
      setActionError(err instanceof ApiRequestError ? err.message : "No se pudo publicar a QCO.");
    } finally {
      setPublishing(false);
    }
  };

  const handleExportExcel = async (): Promise<void> => {
    setActionError(null);
    setExporting(true);
    try {
      await api.exportReleaseTestCases(releaseId, release?.name || "Release");
    } catch (err) {
      setActionError(err instanceof ApiRequestError ? err.message : "No se pudo exportar el Excel.");
    } finally {
      setExporting(false);
    }
  };

  const handleCreateTestCase = async (event: React.FormEvent): Promise<void> => {
    event.preventDefault();
    setSubmitting(true);
    setActionError(null);
    try {
      await api.createTestCase(releaseId, {
        test_case_id: form.test_case_id,
        component: form.component,
        test_case_name: form.test_case_name,
        priority: form.priority,
        test_type: form.test_type,
        ...(release?.operativa_release_id || release?.be_release_id
          ? { device: form.device, device_source: "Alta manual QC" }
          : {}),
      });
      setForm(emptyForm);
      setShowManualForm(false);
      load();
    } catch (err) {
      setActionError(err instanceof ApiRequestError ? err.message : "No se pudo crear el test case.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleInlineStatusChange = async (testCaseId: number, status: TestCase["status"]): Promise<void> => {
    const previous = testCases;
    setTestCases((current) => current.map((tc) => (tc.id === testCaseId ? { ...tc, status } : tc)));
    setActionError(null);
    try {
      await api.updateTestCase(testCaseId, { status });
    } catch (err) {
      setTestCases(previous);
      setActionError(err instanceof ApiRequestError ? err.message : "No se pudo actualizar el estado del Test Case.");
    }
  };

  const handleDeleteTestCase = async (row: TestCase): Promise<void> => {
    const confirmed = window.confirm("¿Deseas eliminar este Test Case?");
    if (!confirmed) {
      return;
    }
    setActionError(null);
    try {
      await api.deleteTestCase(row.id);
      load();
    } catch (err) {
      setActionError(err instanceof ApiRequestError ? err.message : "No se pudo eliminar el Test Case.");
    }
  };

  const handleBulkStatus = async (status: TestCase["status"]): Promise<void> => {
    if (selectedIds.length === 0 || bulkBusy) return;
    setBulkBusy(true);
    setActionError(null);
    setBulkNotice(null);
    try {
      const result = await api.bulkUpdateTestCaseStatus(releaseId, selectedIds, status);
      const text = summarizeBulkResult("status", result.updated.length, result.failed);
      setBulkNotice({ ok: result.failed.length === 0, text });
      setSelectedIds([]);
      load();
    } catch (err) {
      setActionError(err instanceof ApiRequestError ? err.message : "No se pudo cambiar el estado.");
    } finally {
      setBulkBusy(false);
    }
  };

  const handleBulkDelete = async (): Promise<void> => {
    if (selectedIds.length === 0 || bulkBusy) return;
    setBulkBusy(true);
    setActionError(null);
    setBulkNotice(null);
    try {
      const result = await api.bulkDeleteTestCases(releaseId, selectedIds);
      const text = summarizeBulkResult("delete", result.deleted.length, result.failed);
      setBulkNotice({ ok: result.failed.length === 0, text });
      setSelectedIds([]);
      load();
    } catch (err) {
      setActionError(err instanceof ApiRequestError ? err.message : "No se pudo eliminar la selección.");
    } finally {
      setBulkBusy(false);
    }
  };

  const matrixCases = useMemo(
    () => testCases.filter((row) => row.source_type === "qc_matrix"),
    [testCases],
  );
  const rnCases = useMemo(
    () => testCases.filter((row) => row.source_type !== "qc_matrix"),
    [testCases],
  );
  const matrixTabLabel = matrixScopeLabel(release);
  useEffect(() => {
    if (!matrixTabLabel) setCaseTab("rn");
  }, [matrixTabLabel]);
  const scopedCases = caseTab === "matrix" ? matrixCases : rnCases;
  const deviceOptions = useMemo(() => {
    const labels = new Set<string>();
    for (const row of testCases) {
      const label = (row.device || "").trim();
      if (label) {
        labels.add(label);
      }
    }
    return [...labels].sort((a, b) => a.localeCompare(b, "es"));
  }, [testCases]);
  const componentOptions = useMemo(
    () => uniqueSorted(scopedCases.map((row) => componentLabel(row))),
    [scopedCases],
  );
  const storyOptions = useMemo(
    () => uniqueSorted(scopedCases.map((row) => storyLabel(row))),
    [scopedCases],
  );
  const priorityOptions = useMemo(
    () => uniqueSorted(scopedCases.map((row) => row.priority)),
    [scopedCases],
  );
  const statusOptions = useMemo(
    () => uniqueSorted(scopedCases.map((row) => row.status)),
    [scopedCases],
  );

  useEffect(() => {
    const stored = loadReleaseCaseFilters(releaseId);
    setDeviceFilter(stored.device);
    setComponentFilter(stored.component);
    setStoryFilter(stored.story);
    setPriorityFilter(stored.priority);
    setStatusFilter(stored.status);
    skipFilterPersist.current = true;
  }, [releaseId]);

  useEffect(() => {
    if (skipFilterPersist.current) {
      skipFilterPersist.current = false;
      return;
    }
    saveReleaseCaseFilters(releaseId, {
      device: deviceFilter,
      component: pruneFilterList(componentFilter, componentOptions),
      story: pruneFilterList(storyFilter, storyOptions),
      priority: pruneFilterList(priorityFilter, priorityOptions),
      status: pruneFilterList(statusFilter, statusOptions),
    });
  }, [
    releaseId,
    deviceFilter,
    componentFilter,
    storyFilter,
    priorityFilter,
    statusFilter,
    deviceOptions,
    componentOptions,
    storyOptions,
    priorityOptions,
    statusOptions,
  ]);

  const tableFiltersOn = Boolean(
    columnFilterIsActive(componentFilter)
    || columnFilterIsActive(storyFilter)
    || columnFilterIsActive(priorityFilter)
    || columnFilterIsActive(statusFilter),
  );
  const visibleCases = useMemo(
    () =>
      filterReleaseCases(scopedCases, {
        device: deviceFilter,
        component: componentFilter,
        story: storyFilter,
        priority: priorityFilter,
        status: statusFilter,
      }),
    [scopedCases, deviceFilter, componentFilter, storyFilter, priorityFilter, statusFilter],
  );
  const filterSignature = JSON.stringify({
    caseTab,
    deviceFilter,
    componentFilter,
    storyFilter,
    priorityFilter,
    statusFilter,
  });
  useEffect(() => {
    setSelectedIds([]);
  }, [filterSignature, releaseId]);
  const visibleIds = useMemo(() => selectFilteredIds(visibleCases), [visibleCases]);
  const headerSelect = headerCheckboxState(visibleIds, selectedIds);
  useEffect(() => {
    if (headerSelectRef.current) {
      headerSelectRef.current.indeterminate = headerSelect.indeterminate;
    }
  }, [headerSelect.indeterminate, headerSelect.checked]);
  const rnEpicKeys = useMemo(() => rnScopeEpicKeys(analysis), [analysis]);
  const rnCoverage = useMemo(() => rnScopeCoverage(analysis), [analysis]);
  const epicHours = useMemo(
    () => hoursByTechnicalEpic(visibleCases, rnEpicKeys, rnCoverage),
    [visibleCases, rnEpicKeys, rnCoverage],
  );
  const epicProgress = useMemo(
    () => progressByTechnicalEpic(visibleCases, rnEpicKeys, rnCoverage),
    [visibleCases, rnEpicKeys, rnCoverage],
  );

  if (loadError) {
    return (
      <div className="page">
        <p className="error-text">{loadError}</p>
        <p>
          <Link href="/" className="back-link">← Volver al Dashboard</Link>
        </p>
      </div>
    );
  }

  if (!release) {
    return (
      <div className="page">
        <p className="muted">Cargando…</p>
      </div>
    );
  }

  const isBe = Boolean(release.be_release_id);
  const isOperativa = Boolean(release.operativa_release_id);
  const isApp = !isBe && !isOperativa;
  const caseTableCols = 10;
  const backHref = isBe ? "/releases-be" : isOperativa ? "/operativas/release-notes" : "/releases";
  const backLabel = isBe
    ? "← Volver a Release BE"
    : isOperativa
      ? "← Volver a Operativas"
      : "← Volver a Releases";
  const hasEngineCases = testCases.some((row) => row.generated_by_engine);
  const canEditAppsPlanning = isApp && release.status === "IN_PROGRESS" && canChangeReleaseStatus;
  const { hours: caseHours, days: estimationDays } = isOperativa
    ? estimateOperativaEffort(visibleCases)
    : isApp
      ? estimateReleaseEffortFromCases(visibleCases)
      : estimateReleaseEffortLegacyCount(visibleCases.length);
  const scopeHours = isApp
    ? validationScopeHours(
        editingPlanning && canEditAppsPlanning ? planningForm.validationType : release.validation_type,
      )
    : 0;
  const estimationHours = caseHours + scopeHours;
  const qcResources =
    isApp && editingPlanning ? Math.max(1, Number(planningForm.qcResources) || 1) : (release.qc_resources ?? 1);
  const liveExecutionDays =
    isApp && editingPlanning
      ? calculateBusinessDays(planningForm.startDate, planningForm.endDate)
      : release.execution_days;
  const personDays = isApp ? estimationHours / QC_HOURS_PER_DAY : estimationDays;
  const estimatedDurationDays = isApp ? durationDays(personDays, qcResources) : estimationDays;
  const statusCounts = visibleCases.reduce<Record<string, number>>((counts, row) => {
    counts[row.status] = (counts[row.status] || 0) + 1;
    return counts;
  }, {});

  return (
    <div className="page page-wide">
      <p style={{ marginBottom: "1rem" }}>
        <Link href={backHref} className="back-link">{backLabel}</Link>
      </p>
      <p className="eyebrow">{isBe ? "Release BE" : "Release"}</p>
      <h1>
        {release.name}
        {!isOperativa && !isBe && (
          <>
            {" "}
            <span className="muted">v{release.version}</span>
          </>
        )}
      </h1>
      <p className="subtitle">
        {isOperativa || isBe ? (
          <StatusBadge status={release.status} />
        ) : (
          <>
            {release.platform}
            {release.cluster ? ` · ${release.cluster}` : ""} · <StatusBadge status={release.status} />
          </>
        )}
      </p>

      <div className="card" style={{ marginTop: "1rem" }}>
        {canEditAppsPlanning && (
          <div className="form-actions" style={{ justifyContent: "flex-end", marginBottom: "10px" }}>
            {!editingPlanning ? (
              <button type="button" className="secondary" onClick={beginEditPlanning}>
                Editar planificación
              </button>
            ) : (
              <>
                <button
                  type="button"
                  className="secondary"
                  disabled={planningBusy}
                  onClick={() => {
                    setEditingPlanning(false);
                    setActionError(null);
                  }}
                >
                  Cancelar
                </button>
                <button type="button" disabled={planningBusy} onClick={() => void savePlanning()}>
                  {planningBusy ? "Guardando…" : "Guardar"}
                </button>
              </>
            )}
          </div>
        )}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "12px", fontSize: "12.5px" }}>
          {isBe ? (
            <>
              <div>
                <span className="muted" style={{ display: "block", fontSize: "11px", textTransform: "uppercase" }}>Entregable</span>
                <span style={{ fontWeight: 600 }}>{release.deliverable_name ?? "—"}</span>
              </div>
              <div>
                <span className="muted" style={{ display: "block", fontSize: "11px", textTransform: "uppercase" }}>Nombre</span>
                <span style={{ fontWeight: 600 }}>{release.name}</span>
              </div>
              <div>
                <span className="muted" style={{ display: "block", fontSize: "11px", textTransform: "uppercase" }}>SWF</span>
                <span style={{ fontWeight: 600 }}>{release.swf ?? "—"}</span>
              </div>
              <div>
                <span className="muted" style={{ display: "block", fontSize: "11px", textTransform: "uppercase" }}>Cluster</span>
                <span style={{ fontWeight: 600 }}>{release.cluster ?? "—"}</span>
              </div>
              <div>
                <span className="muted" style={{ display: "block", fontSize: "11px", textTransform: "uppercase" }}>Alcance QC</span>
                <span style={{ fontWeight: 600 }}>
                  {release.validation_type || release.regresivo_scope || "—"}
                </span>
              </div>
            </>
          ) : (
            <>
              <div>
                <span className="muted" style={{ display: "block", fontSize: "11px", textTransform: "uppercase" }}>Entregable</span>
                <span style={{ fontWeight: 600 }}>{release.deliverable_name ?? "—"}</span>
              </div>
              {!isOperativa && (
                <>
                  <div>
                    <span className="muted" style={{ display: "block", fontSize: "11px", textTransform: "uppercase" }}>Tipo de Release</span>
                    <span style={{ fontWeight: 600 }}>
                      {release.release_type === "NUEVO"
                        ? "Nuevo"
                        : release.release_type === "REVALIDACION"
                          ? "Revalidación"
                          : "—"}
                    </span>
                  </div>
                  <div>
                    <span className="muted" style={{ display: "block", fontSize: "11px", textTransform: "uppercase" }}>Release origen</span>
                    <span style={{ fontWeight: 600 }}>{release.parent_release_name ?? "—"}</span>
                  </div>
                </>
              )}
              {editingPlanning && canEditAppsPlanning ? (
                <>
                  <div>
                    <span className="muted" style={{ display: "block", fontSize: "11px", textTransform: "uppercase" }}>Inicio</span>
                    <input
                      type="date"
                      value={planningForm.startDate}
                      onChange={(e) => setPlanningForm({ ...planningForm, startDate: e.target.value })}
                      style={{ marginTop: "4px", width: "100%", minWidth: "11rem", position: "relative", zIndex: 2 }}
                    />
                  </div>
                  <div>
                    <span className="muted" style={{ display: "block", fontSize: "11px", textTransform: "uppercase" }}>Fin</span>
                    <input
                      type="date"
                      min={planningForm.startDate || undefined}
                      value={planningForm.endDate}
                      onChange={(e) => setPlanningForm({ ...planningForm, endDate: e.target.value })}
                      style={{ marginTop: "4px", width: "100%", minWidth: "11rem", position: "relative", zIndex: 2 }}
                    />
                  </div>
                </>
              ) : (
              <div>
                <span className="muted" style={{ display: "block", fontSize: "11px", textTransform: "uppercase" }}>Ventana de revisión</span>
                  <span style={{ fontWeight: 600 }}>
                    {formatDate(release.start_date)} — {formatDate(release.end_date)}
                  </span>
              </div>
              )}
              <div>
                <span className="muted" style={{ display: "block", fontSize: "11px", textTransform: "uppercase" }}>Ventana de ejecución</span>
                <span style={{ fontWeight: 600, color: "var(--accent)" }}>
                  {liveExecutionDays ? `${liveExecutionDays} días hábiles` : "—"}
                </span>
              </div>
              {isOperativa ? (
                <div>
                  <span className="muted" style={{ display: "block", fontSize: "11px", textTransform: "uppercase" }}>Cluster</span>
                  <span style={{ fontWeight: 600 }}>{release.cluster ?? "—"}</span>
                </div>
              ) : (
                <>
                  <div>
                    <span className="muted" style={{ display: "block", fontSize: "11px", textTransform: "uppercase" }}>Recursos QC</span>
                    {editingPlanning && canEditAppsPlanning ? (
                      <input
                        type="number"
                        min={1}
                        max={50}
                        value={planningForm.qcResources}
                        onChange={(e) => setPlanningForm({ ...planningForm, qcResources: Number(e.target.value) || 1 })}
                        style={{ marginTop: "4px", width: "80px" }}
                      />
                    ) : (
                      <span style={{ fontWeight: 600 }}>{release.qc_resources ?? 1} recurso(s)</span>
                    )}
                  </div>
                  <div>
                    <span className="muted" style={{ display: "block", fontSize: "11px", textTransform: "uppercase" }}>Alcance de validación</span>
                    {editingPlanning && canEditAppsPlanning ? (
                      <ValidationScopeSelect
                        id="planning-validation-type"
                        helpId="planning-validation-help"
                        value={planningForm.validationType}
                        onChange={(validationType) => setPlanningForm({ ...planningForm, validationType })}
                        style={{ marginTop: "4px" }}
                      />
                    ) : (
                      <span style={{ fontWeight: 600 }}>{release.validation_type?.trim() || "—"}</span>
                    )}
                  </div>
                </>
              )}
            </>
          )}
          {(isApp || isBe) && (
            <div style={{ gridColumn: "1 / -1" }}>
              <ValidationScopeSummary
                id="planning-validation-help"
                value={
                  isBe
                    ? (release.validation_type || release.regresivo_scope)
                    : editingPlanning && canEditAppsPlanning
                      ? planningForm.validationType
                      : release.validation_type
                }
                qcResources={editingPlanning && canEditAppsPlanning ? planningForm.qcResources : release.qc_resources}
                matrixCaseCount={matrixImpact?.caseCount}
                matrixNote={matrixImpact?.note}
                hideEstimate={matrixImpact?.estimateInSection === true}
              />
              <MatrixScopeEditor
                variant="summary"
                platform={release.platform}
                cluster={release.cluster}
                validationType={
                  isBe
                    ? (release.validation_type || release.regresivo_scope || "")
                    : editingPlanning && canEditAppsPlanning
                      ? planningForm.validationType
                      : (release.validation_type ?? "")
                }
                rawAnalysis={analysis?.raw_analysis}
                releaseId={release.id}
                touchedModules={release.qc_matrix_touched_modules ?? null}
                templateValues={release.qc_matrix_template_values ?? null}
                qcResources={editingPlanning && canEditAppsPlanning ? planningForm.qcResources : release.qc_resources}
                readOnly
                onTouchedModules={() => undefined}
                onTemplateValues={() => undefined}
                onPreview={setMatrixImpact}
              />
            </div>
          )}
          {(release.jira_issue_filter || canEditAppsPlanning) && !isBe && (
            <div style={{ gridColumn: "1 / -1" }}>
              <span className="muted" style={{ display: "block", fontSize: "11px", textTransform: "uppercase" }}>Filtro de issues (Jira)</span>
              {editingPlanning && canEditAppsPlanning ? (
                <input
                  value={planningForm.jiraIssueFilter}
                  onChange={(e) => setPlanningForm({ ...planningForm, jiraIssueFilter: e.target.value })}
                  placeholder="https://dlatvarg.atlassian.net/issues/?filter=123456"
                  style={{ marginTop: "4px", width: "100%" }}
                />
              ) : (
                <code style={{ fontSize: "12px", background: "var(--surface-2)", padding: "3px 8px", borderRadius: "4px" }}>
                  {parseJiraFilterId(release.jira_issue_filter) ? (
                    <JiraFilterLink filterId={parseJiraFilterId(release.jira_issue_filter)} />
                  ) : release.jira_issue_filter?.startsWith("http") ? (
                    <a href={release.jira_issue_filter} target="_blank" rel="noopener noreferrer">
                      {release.jira_issue_filter}
                    </a>
                  ) : (
                    release.jira_issue_filter || "—"
                  )}
                </code>
              )}
            </div>
          )}
          {(release.description || canEditAppsPlanning) && (
            <div style={{ gridColumn: "1 / -1", marginTop: "4px" }}>
              <span className="muted" style={{ display: "block", fontSize: "11px", textTransform: "uppercase" }}>Descripción</span>
              {editingPlanning && canEditAppsPlanning ? (
                <textarea
                  value={planningForm.description}
                  onChange={(e) => setPlanningForm({ ...planningForm, description: e.target.value })}
                  rows={3}
                  style={{ marginTop: "4px", width: "100%" }}
                />
              ) : (
                <p style={{ margin: "2px 0 0" }}>{release.description || "—"}</p>
              )}
            </div>
          )}
          {editingPlanning && canEditAppsPlanning && hasEngineCases && (
            <p className="muted" style={{ gridColumn: "1 / -1", margin: "4px 0 0", fontSize: "12px" }}>
              Cambiar el alcance de validación o el filtro no regenera los Test Cases. La duración de abajo sí se actualiza con los recursos.
            </p>
          )}
        </div>
      </div>

      {isBe ? null : isOperativa ? (
        <div className="card" style={{ marginTop: "1rem" }}>
          <h2>Análisis de Release</h2>
          <p className="muted" style={{ fontSize: "12px", margin: "0 0 12px" }}>
            EPCs incluidos al crear este Release. La selección está congelada.
          </p>
          <OperativaEpcTable epcs={includedEpcs} readOnly />
        </div>
      ) : (
        analysis && (
          <div style={{ marginTop: "1rem" }}>
            <ReleaseAnalysisCard
              analysis={analysis}
              releaseId={releaseId}
              qcResources={qcResources}
              executionDays={liveExecutionDays}
              effortHours={isApp ? estimationHours : null}
              personDays={isApp ? personDays : null}
              durationDays={isApp ? estimatedDurationDays : null}
            />
          </div>
        )
      )}

      {isOperativa && coverageMatrix && <OperativaCoverageMatrix data={coverageMatrix} />}

      {actionError && <p className="error-text">{actionError}</p>}
      {generateResult && (
        <div className="import-issues warning" style={{ marginTop: "10px" }}>
          <div className="import-issues-title">
            <Sparkles size={14} aria-hidden="true" />
            {isBe ? "Estado de Matrices QC" : "Estado del Motor QC"}
          </div>
          {(generateResult.message || "")
            .split("\n")
            .filter((line) => line && line !== "Ver detalles del análisis")
            .map((line) => (
              <p key={line} style={{ margin: "0 0 4px" }}>
                {line}
              </p>
            ))}
          {(generateResult.analysis_details?.length ?? 0) > 0 && (
            <>
              <button
                type="button"
                onClick={() => setShowAnalysisDetails((open) => !open)}
                style={{ marginTop: "4px" }}
              >
                {showAnalysisDetails ? "Ocultar detalles del análisis" : "Ver detalles del análisis"}
              </button>
              {showAnalysisDetails && (
                <ul style={{ marginTop: "8px" }}>
                  {generateResult.analysis_details?.map((detail) => (
                    <li key={detail}>{detail}</li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      )}

      {SHOW_QCO_ZEPHYR_PUBLISH && publishResult && (
        <div className="import-issues warning" style={{ marginTop: "10px" }}>
          <div className="import-issues-title">Publicación QCO</div>
          <p style={{ margin: "0 0 4px" }}>{publishResult.message}</p>
          <p className="muted" style={{ margin: 0 }}>
            Enviados {publishResult.sent} · Creados {publishResult.created} · Duplicados {publishResult.duplicates} ·
            Errores {publishResult.errors}
            {publishResult.caseforge_unmodified ? " · QC Pulse sin modificación" : " · Atención: fingerprints cambiaron"}
          </p>
        </div>
      )}

      {/* Lifecycle Actions */}
      {(canChangeReleaseStatus || canDeleteRelease) && (
      <div className="card" style={{ position: "relative", zIndex: 2 }}>
        <h2>Acciones de Ciclo de Vida</h2>
        {actionError && <p className="error-text">{actionError}</p>}
        <div className="form-actions">
          {canChangeReleaseStatus && (NEXT_STATUS[release.status] ?? []).map((next) => (
            <button
              key={next}
              type="button"
              disabled={statusBusy}
              onClick={() => void handleStatusChange(next)}
            >
              {statusBusy ? "Guardando…" : `Mover a ${next}`}
            </button>
          ))}
          {canDeleteRelease && (
          <button
            type="button"
            className="danger"
            disabled={statusBusy}
            onClick={() => void handleDelete()}
          >
            Eliminar
          </button>
          )}
        </div>
      </div>
      )}

      {isApp ? <CaseProgressSummary title="Total de la Release" rows={testCases} /> : null}
      {matrixTabLabel ? (
        <div className="tabnav" role="tablist">
          <button type="button" role="tab" className={caseTab === "rn" ? "active" : ""} onClick={() => setCaseTab("rn")}>
            Alcance (RN/EPC)
          </button>
          <button type="button" role="tab" className={caseTab === "matrix" ? "active" : ""} onClick={() => setCaseTab("matrix")}>
            {matrixTabLabel}
          </button>
        </div>
      ) : null}

      {/* Test Cases Section */}
      <div className="section-header">
        <h2>
          {caseTab === "matrix" && matrixTabLabel ? matrixTabLabel : "Test Cases"} ({visibleCases.length}
          {deviceFilter || tableFiltersOn ? ` / ${scopedCases.length}` : ""})
        </h2>
        <div className="form-actions" style={{ margin: 0 }}>
          {canLoadRn && (
          <button
            type="button"
            onClick={() => void handleGenerateCases(hasEngineCases)}
            disabled={generating}
            style={{ background: "var(--accent-dim)", color: "#a9c8fb", border: "1px solid var(--accent)" }}
          >
            <Sparkles size={14} aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: "6px" }} />
            {generating
              ? "Generando…"
              : isBe
                ? "Generar casos desde Matriz"
                : isOperativa
                  ? (hasEngineCases ? "Regenerar casos" : "Generar casos")
                  : hasEngineCases
                    ? "Regenerar casos desde RN"
                    : "Generar casos desde RN"}
          </button>
          )}
          {canLoadRn && SHOW_QCO_ZEPHYR_PUBLISH && isOperativa && hasEngineCases && (
            <button
              type="button"
              className="secondary"
              onClick={() => void handlePublishQco()}
              disabled={publishing}
            >
              {publishing ? "Publicando en QCO…" : "Publicar en QCO"}
            </button>
          )}
          <button type="button" className="secondary" onClick={() => void handleExportExcel()} disabled={exporting || testCases.length === 0}>
            <Download size={14} aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: "6px" }} />
            {exporting ? "Exportando…" : "Exportar Excel"}
          </button>
          {canLoadRn && (
          <button type="button" onClick={() => { setShowImport((v) => !v); setShowManualForm(false); }}>
            <Upload size={14} aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: "6px" }} />
            Importar Test Cases
          </button>
          )}
          {canLoadRn && (
          <button type="button" className="secondary" onClick={() => {
            setShowImport(false);
            setShowManualForm((open) => {
              const next = !open;
              if (next) {
                setForm({
                  ...emptyForm,
                  test_case_id: nextTestCaseId(testCases.map((row) => row.test_case_id)),
                });
              }
              return next;
            });
          }}>
            <Plus size={14} aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: "6px" }} />
            Nuevo Test Case
          </button>
          )}
        </div>
      </div>

      {isApp ? (
        <CaseProgressSummary
          title={caseTab === "matrix" && matrixTabLabel ? matrixTabLabel : "Alcance (RN/EPC)"}
          rows={scopedCases}
        />
      ) : null}
      {(isApp ? caseTab === "rn" && rnCases.length > 0 : testCases.length > 0) && (
        <>
          {(isOperativa || isBe) && deviceOptions.length > 0 && (
            <div className="form-actions" style={{ marginBottom: "10px", alignItems: "center" }}>
              <label htmlFor="device-filter" className="muted" style={{ margin: 0 }}>
                Dispositivo
              </label>
              <select
                id="device-filter"
                value={deviceFilter}
                onChange={(e) => setDeviceFilter(e.target.value)}
                style={{ minWidth: "200px" }}
              >
                <option value="">Todos los dispositivos</option>
                {deviceOptions.map((device) => (
                  <option key={device} value={device}>
                    {device}
                  </option>
                ))}
              </select>
            </div>
          )}
          {(tableFiltersOn || deviceFilter) && (
            <div className="form-actions" style={{ marginBottom: "10px" }}>
              <button
                type="button"
                className="secondary"
                onClick={() => {
                  setDeviceFilter("");
                  setComponentFilter(null);
                  setStoryFilter(null);
                  setPriorityFilter(null);
                  setStatusFilter(null);
                }}
              >
                Quitar filtros
              </button>
            </div>
          )}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
            gap: "10px",
            marginBottom: "12px",
          }}
        >
          {[
            { label: "Test Cases", value: String(visibleCases.length) },
            ...(isOperativa
              ? [
                  { label: "Esfuerzo estimado QC", value: `${estimationHours.toFixed(1)} h`, tip: QC_OPERATIVA_ESTIMATION_TOOLTIP },
                  { label: "Duración estimada", value: `${estimationDays.toFixed(1)} días` },
                ]
              : isApp
                ? [
                    { label: "Esfuerzo estimado QC", value: `${estimationHours.toFixed(1)} h`, tip: QC_ESTIMATION_TOOLTIP },
                    { label: "Días-persona", value: personDays.toFixed(1) },
                    { label: "Duración estimada", value: `${estimatedDurationDays.toFixed(1)} días` },
                    { label: "Recursos QC", value: String(qcResources) },
                  ]
                : [
                    { label: "Esfuerzo estimado QC", value: `${estimationHours.toFixed(1)} h`, tip: QC_ESTIMATION_TOOLTIP },
                    { label: "≈ Días QC", value: estimationDays.toFixed(1) },
                  ]),
            { label: "UNEXECUTED", value: String(statusCounts.UNEXECUTED || 0) },
            { label: "PASS", value: String(statusCounts.PASS || 0) },
            { label: "FAIL", value: String(statusCounts.FAIL || 0) },
          ].map((stat) => (
            <div
              key={stat.label}
              style={{
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
                borderRadius: "8px",
                padding: "10px 14px",
              }}
            >
              <div style={{ fontSize: "10.5px", textTransform: "uppercase", letterSpacing: ".04em", color: "var(--text-dim)" }}>
                {stat.label}
                {"tip" in stat && stat.tip ? <InfoTooltip text={stat.tip} /> : null}
              </div>
              <div style={{ fontSize: "20px", fontWeight: 700, marginTop: "2px" }}>{stat.value}</div>
            </div>
          ))}
        </div>
        {isApp && caseTab === "rn" && <EpicHoursPanel items={epicHours} fileName={release.name} />}
        {isApp && caseTab === "rn" && <EpicProgressPanel rows={epicProgress} />}
        </>
      )}

      {showImport && (
        <ImportTestCasesPanel
          releaseId={releaseId}
          onClose={() => setShowImport(false)}
          onImported={load}
        />
      )}

      {showManualForm && (
        <div className="card">
          <h2>Nuevo Test Case</h2>
          <p className="muted" style={{ fontSize: "12.5px", marginTop: "-6px" }}>
            Alta manual — para cargas masivas usa &quot;Importar Test Cases&quot; o &quot;{isBe ? "Generar casos desde Matriz" : "Generar casos desde RN"}&quot;.
          </p>
          <form onSubmit={handleCreateTestCase}>
            <div className="form-grid">
              <div className="form-field">
                <label htmlFor="test_case_id">Test Case ID</label>
                <input
                  id="test_case_id"
                  required
                  placeholder="QC-001"
                  value={form.test_case_id}
                  onChange={(e) => setForm({ ...form, test_case_id: e.target.value })}
                />
              </div>
              <div className="form-field">
                <label htmlFor="component">Componente</label>
                <input
                  id="component"
                  required
                  value={form.component}
                  onChange={(e) => setForm({ ...form, component: e.target.value })}
                />
              </div>
              {isOperativa || isBe ? (
                <div className="form-field">
                  <label htmlFor="device">Dispositivo</label>
                  <select
                    id="device"
                    required
                    value={form.device}
                    onChange={(e) => setForm({ ...form, device: e.target.value })}
                  >
                    <option value="">Seleccionar…</option>
                    {Array.from(
                      new Set([...deviceOptions, ...OPERATIVA_DEVICE_OPTIONS]),
                    ).map((device) => (
                      <option key={device} value={device}>
                        {device}
                      </option>
                    ))}
                  </select>
                </div>
              ) : null}
              <div className="form-field full">
                <label htmlFor="test_case_name">Nombre</label>
                <input
                  id="test_case_name"
                  required
                  value={form.test_case_name}
                  onChange={(e) => setForm({ ...form, test_case_name: e.target.value })}
                />
              </div>
              <div className="form-field">
                <label htmlFor="priority">Prioridad</label>
                <select
                  id="priority"
                  value={form.priority}
                  onChange={(e) => setForm({ ...form, priority: e.target.value as TestCase["priority"] })}
                >
                  <option value="BLOCKER">BLOCKER</option>
                  <option value="CRITICAL">CRITICAL</option>
                </select>
              </div>
              <div className="form-field">
                <label htmlFor="test_type">Tipo</label>
                <select
                  id="test_type"
                  value={form.test_type}
                  onChange={(e) => setForm({ ...form, test_type: e.target.value as TestCase["test_type"] })}
                >
                  <option value="FUNCTIONAL">FUNCTIONAL</option>
                  <option value="REGRESSION">REGRESSION</option>
                  <option value="SMOKE">SMOKE</option>
                  <option value="UI">UI</option>
                  <option value="PERFORMANCE">PERFORMANCE</option>
                  <option value="OTHER">OTHER</option>
                </select>
              </div>
            </div>
            <div className="form-actions">
              <button type="submit" disabled={submitting}>
                {submitting ? "Creando…" : "Crear Test Case"}
              </button>
            </div>
          </form>
        </div>
      )}

      {bulkNotice && (
        <p className={bulkNotice.ok ? "muted" : "error-text"}>{bulkNotice.text}</p>
      )}
      {canExecuteCases && selectedIds.length > 0 && (
        <TestCaseBulkBar
          count={selectedIds.length}
          busy={bulkBusy}
          onClear={() => setSelectedIds([])}
          onChangeStatus={handleBulkStatus}
          onDelete={handleBulkDelete}
        />
      )}

      <table className="case-grid">
        <thead>
          <tr>
            <th className="select">
              {canExecuteCases && visibleIds.length > 0 ? (
                <input
                  ref={headerSelectRef}
                  type="checkbox"
                  checked={headerSelect.checked}
                  disabled={bulkBusy}
                  aria-label={`Seleccionar los ${visibleIds.length} resultados filtrados`}
                  title={`Seleccionar los ${visibleIds.length} resultados filtrados`}
                  onChange={() =>
                    setSelectedIds(headerSelect.checked ? [] : visibleIds)
                  }
                />
              ) : null}
            </th>
            <th>ID</th>
            <th>Nombre</th>
            <th className="steps">Pasos</th>
            {isApp ? <th>Issue Type</th> : null}
            <th>
              {testCases.length > 0 ? (
                <ColumnFilter
                  label="Componente"
                  options={componentOptions}
                  selected={componentFilter}
                  onChange={setComponentFilter}
                />
              ) : (
                "Componente"
              )}
            </th>
            {isApp ? (
              <th>
                {testCases.length > 0 ? (
                  <ColumnFilter
                    label="Technical Story"
                    options={storyOptions}
                    selected={storyFilter}
                    onChange={setStoryFilter}
                  />
                ) : (
                  "Technical Story"
                )}
              </th>
            ) : (
              <>
                <th>Ecosistema</th>
                <th>Dispositivo</th>
              </>
            )}
            <th>
              {testCases.length > 0 ? (
                <ColumnFilter
                  label="Prioridad"
                  options={priorityOptions}
                  selected={priorityFilter}
                  onChange={setPriorityFilter}
                />
              ) : (
                "Prioridad"
              )}
            </th>
            <th>
              {testCases.length > 0 ? (
                <ColumnFilter
                  label="Estado"
                  options={statusOptions}
                  selected={statusFilter}
                  onChange={setStatusFilter}
                  formatOption={(value) => (value === "N_A" ? "N/A" : value)}
                />
              ) : (
                "Estado"
              )}
            </th>
            <th>Acciones</th>
          </tr>
        </thead>
        <tbody>
          {visibleCases.map((testCase) => (
            <tr
              key={testCase.id}
              className="clickable"
              onClick={() => router.push(`/test-cases/${testCase.id}`)}
            >
              <td className="select" onClick={(e) => e.stopPropagation()}>
                {canExecuteCases ? (
                  <input
                    type="checkbox"
                    checked={selectedIds.includes(testCase.id)}
                    disabled={bulkBusy}
                    aria-label={`Seleccionar ${testCase.test_case_id}`}
                    onChange={() => setSelectedIds((current) => toggleSelectedId(current, testCase.id))}
                  />
                ) : null}
              </td>
              <td>{testCase.test_case_id}</td>
              <td>{isOperativa ? stripDeviceFromCaseName(testCase.test_case_name, testCase.device) : testCase.test_case_name}</td>
              <td className={testCase.step_count ? "steps" : "steps muted"} title={`${testCase.step_count ?? 0} pasos`}>
                {testCase.step_count ?? 0}
              </td>
              {isApp ? (
                <td>
                  {testCase.source_type === "qc_matrix"
                    ? (release.validation_type?.trim() || "—")
                    : formatRnSourceType(testCase.source_type)}
                </td>
              ) : null}
              {isApp ? (
                <td onClick={(e) => e.stopPropagation()}>
                  <JiraKeyText value={testCase.component || testCase.technical_epic} />
                </td>
              ) : (
                <td>{testCase.component}</td>
              )}
              {isApp ? (
                <td>{testCase.technical_story?.trim() || "—"}</td>
              ) : (
                <>
                  <td>{testCase.ecosystem ?? "—"}</td>
                  <td>{testCase.device ?? "—"}</td>
                </>
              )}
              <td>{testCase.priority}</td>
              <td onClick={(e) => e.stopPropagation()}>
                {canExecuteCases ? (
                <select
                  value={testCase.status}
                  onChange={(e) => void handleInlineStatusChange(testCase.id, e.target.value as TestCase["status"])}
                  className={`status-select status-select-${testCase.status.toLowerCase()}`}
                >
                  <option value="UNEXECUTED">UNEXECUTED</option>
                  <option value="PASS">PASS</option>
                  <option value="FAIL">FAIL</option>
                  <option value="BLOCKED">BLOCKED</option>
                  <option value="N_A">N/A</option>
                </select>
                ) : (
                  <StatusBadge status={testCase.status} />
                )}
              </td>
              <td onClick={(e) => e.stopPropagation()}>
                {canExecuteCases ? (
                  <div className="row-actions">
                    <button
                      type="button"
                      className="icon-btn"
                      title="Editar"
                      aria-label="Editar"
                      onClick={() => setEditingCase(testCase)}
                    >
                      <Pencil size={14} aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      className="icon-btn danger"
                      title="Eliminar"
                      aria-label="Eliminar"
                      onClick={() => void handleDeleteTestCase(testCase)}
                    >
                      <Trash2 size={14} aria-hidden="true" />
                    </button>
                  </div>
                ) : (
                  <span className="muted">—</span>
                )}
              </td>
            </tr>
          ))}
          {visibleCases.length === 0 && (
            <tr>
              <td colSpan={caseTableCols} className="muted">
                {testCases.length === 0
                  ? "Sin test cases todavía."
                  : "Ningún Test Case con esos filtros."}
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <p style={{ marginTop: "1.5rem" }}>
        <Link href={backHref} className="back-link">{backLabel}</Link>
      </p>

      {editingCase && (
        <EditTestCaseModal
          releaseId={releaseId}
          testCase={editingCase}
          onClose={() => setEditingCase(null)}
          onSaved={() => {
            setEditingCase(null);
            load();
          }}
        />
      )}
    </div>
  );
}

const MATRIX_SCOPE_LABELS = new Set([
  "Pruebas Acotadas",
  "Smoke Test",
  "Regresivo",
  "No Afectación",
  "Regresión completa",
]);

function matrixScopeLabel(release: Release | null): string | null {
  if (!release || release.be_release_id || release.operativa_release_id) return null;
  const label = (release.validation_type || "").trim();
  return MATRIX_SCOPE_LABELS.has(label) ? label : null;
}

function CaseProgressSummary({ title, rows }: { title: string; rows: TestCase[] }): React.ReactElement {
  const executed = rows.filter((row) => row.status !== "UNEXECUTED").length;
  const pass = rows.filter((row) => row.status === "PASS").length;
  const fail = rows.filter((row) => row.status === "FAIL").length;
  const percent = rows.length === 0 ? 0 : Math.round((executed / rows.length) * 100);
  const stats = [
    { label: "Total", value: String(rows.length) },
    { label: "Ejecutados", value: String(executed) },
    { label: "% avance", value: `${percent}%` },
    { label: "Pass", value: String(pass) },
    { label: "Fail", value: String(fail) },
  ];
  return (
    <div style={{ marginBottom: "12px" }}>
      <div style={{ fontSize: "12px", fontWeight: 650, marginBottom: "6px" }}>{title}</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: "8px" }}>
        {stats.map((stat) => (
          <div key={stat.label} style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", padding: "8px 12px" }}>
            <div style={{ fontSize: "10.5px", textTransform: "uppercase", letterSpacing: ".04em", color: "var(--text-dim)" }}>{stat.label}</div>
            <div style={{ fontSize: "18px", fontWeight: 700 }}>{stat.value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function JiraKeyText({ value }: { value?: string | null }): React.ReactElement {
  const raw = (value ?? "").trim();
  if (!raw) {
    return <span className="muted">—</span>;
  }
  const keys = parseJiraTicketKeys(raw);
  if (keys.length === 0) {
    return <>{raw}</>;
  }
  const parts: React.ReactNode[] = [];
  const splitter = /\b([A-Z][A-Z0-9_]+-\d+)\b/gi;
  let last = 0;
  let index = 0;
  for (const match of raw.matchAll(splitter)) {
    const start = match.index ?? 0;
    if (start > last) {
      parts.push(raw.slice(last, start));
    }
    const key = match[1].toUpperCase();
    const href = jiraIssueUrl(key);
    parts.push(
      href ? (
        <a key={`${key}-${index}`} href={href} target="_blank" rel="noopener noreferrer" title={`Abrir ${key} en Jira`}>
          {match[0]}
        </a>
      ) : (
        match[0]
      ),
    );
    index += 1;
    last = start + match[0].length;
  }
  if (last < raw.length) {
    parts.push(raw.slice(last));
  }
  return <>{parts}</>;
}
