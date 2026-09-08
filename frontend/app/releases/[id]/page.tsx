"use client";

import { Download, Pencil, Plus, Sparkles, Trash2, Upload } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { EditTestCaseModal } from "@/app/components/EditTestCaseModal";
import { ImportTestCasesPanel } from "@/app/components/ImportTestCasesPanel";
import { InfoTooltip } from "@/app/components/InfoTooltip";
import { OperativaCoverageMatrix } from "@/app/components/OperativaCoverageMatrix";
import { OperativaEpcTable } from "@/app/components/OperativaEpcTable";
import { ReleaseAnalysisCard } from "@/app/components/ReleaseAnalysisCard";
import { StatusBadge } from "@/app/components/StatusBadge";
import { api, ApiRequestError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { BE_REGRESIVO_SCOPE_LABEL, SHOW_QCO_ZEPHYR_PUBLISH } from "@/lib/constants";
import { QC_ESTIMATION_TOOLTIP, QC_OPERATIVA_ESTIMATION_TOOLTIP, estimateOperativaEffort, estimateReleaseEffort, stripDeviceFromCaseName } from "@/lib/qcEffort";
import type { CoverageMatrixResponse, EpcRead, GenerateCasesResponse, PublishCasesResponse, Release, ReleaseAnalysis, ReleaseStatus, TestCase } from "@/lib/types";

const emptyForm = {
  test_case_id: "",
  component: "",
  test_case_name: "",
  priority: "CRITICAL" as TestCase["priority"],
  test_type: "FUNCTIONAL" as TestCase["test_type"],
};

const NEXT_STATUS: Partial<Record<ReleaseStatus, ReleaseStatus[]>> = {
  DRAFT: ["IN_PROGRESS", "CANCELLED"],
  IN_PROGRESS: ["COMPLETED", "CANCELLED"],
};

function formatDate(isoDate?: string | null): string {
  if (!isoDate) return "—";
  const [y, m, d] = isoDate.split("-");
  return `${d}/${m}/${y}`;
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
    setActionError(null);
    setStatusBusy(true);
    try {
      const updated = await api.updateRelease(releaseId, { status });
      setRelease(updated);
    } catch (err) {
      setActionError(err instanceof ApiRequestError ? err.message : "No se pudo actualizar el estado.");
    } finally {
      setStatusBusy(false);
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
      const res = await api.generateCasesFromRN(releaseId, regenerate);
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
      await api.createTestCase(releaseId, form);
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
  const visibleCases = useMemo(() => {
    if (!deviceFilter) {
      return testCases;
    }
    return testCases.filter((row) => (row.device || "").trim() === deviceFilter);
  }, [testCases, deviceFilter]);

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
  const backHref = isBe ? "/releases-be" : isOperativa ? "/operativas/release-notes" : "/releases";
  const backLabel = isBe
    ? "← Volver a Release BE"
    : isOperativa
      ? "← Volver a Operativas"
      : "← Volver a Releases";
  const hasEngineCases = testCases.some((row) => row.generated_by_engine);
  const { hours: estimationHours, days: estimationDays } = isOperativa
    ? estimateOperativaEffort(visibleCases)
    : estimateReleaseEffort(visibleCases.length);
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
                <span className="muted" style={{ display: "block", fontSize: "11px", textTransform: "uppercase" }}>Alcance de regresivo</span>
                <span style={{ fontWeight: 600 }}>
                  {release.regresivo_scope
                    ? BE_REGRESIVO_SCOPE_LABEL[release.regresivo_scope]
                    : "—"}
                </span>
              </div>
              {release.regresivo_scope === "ACOTADO" && (
                <div style={{ gridColumn: "1 / -1" }}>
                  <span className="muted" style={{ display: "block", fontSize: "11px", textTransform: "uppercase" }}>Componente / Funcionalidad Afectada</span>
                  <span style={{ fontWeight: 600 }}>{release.affected_component ?? "—"}</span>
                </div>
              )}
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
              <div>
                <span className="muted" style={{ display: "block", fontSize: "11px", textTransform: "uppercase" }}>Ventana de revisión</span>
                <span style={{ fontWeight: 600 }}>
                  {formatDate(release.start_date)} — {formatDate(release.end_date)}
                </span>
              </div>
              <div>
                <span className="muted" style={{ display: "block", fontSize: "11px", textTransform: "uppercase" }}>Días de ejecución</span>
                <span style={{ fontWeight: 600, color: "var(--accent)" }}>
                  {release.execution_days ? `${release.execution_days} días hábiles` : "—"}
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
                    <span style={{ fontWeight: 600 }}>{release.qc_resources ?? 1} recurso(s)</span>
                  </div>
                  <div>
                    <span className="muted" style={{ display: "block", fontSize: "11px", textTransform: "uppercase" }}>Tipo de validación</span>
                    <span style={{ fontWeight: 600 }}>{release.validation_type ?? "Smoke"}</span>
                  </div>
                </>
              )}
            </>
          )}
          {release.jira_issue_filter && !isBe && (
            <div style={{ gridColumn: "1 / -1" }}>
              <span className="muted" style={{ display: "block", fontSize: "11px", textTransform: "uppercase" }}>Filtro de issues (Jira)</span>
              <code style={{ fontSize: "12px", background: "var(--surface-2)", padding: "3px 8px", borderRadius: "4px" }}>
                {release.jira_issue_filter}
              </code>
            </div>
          )}
          {release.description && (
            <div style={{ gridColumn: "1 / -1", marginTop: "4px" }}>
              <span className="muted" style={{ display: "block", fontSize: "11px", textTransform: "uppercase" }}>Descripción</span>
              <p style={{ margin: "2px 0 0" }}>{release.description}</p>
            </div>
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
              qcResources={release.qc_resources}
              executionDays={release.execution_days}
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

      {/* Test Cases Section */}
      <div className="section-header">
        <h2>Test Cases ({visibleCases.length}{deviceFilter ? ` / ${testCases.length}` : ""})</h2>
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
          <button type="button" className="secondary" onClick={() => { setShowManualForm((v) => !v); setShowImport(false); }}>
            <Plus size={14} aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: "6px" }} />
            Nuevo Test Case
          </button>
          )}
        </div>
      </div>

      {testCases.length > 0 && (
        <>
          {isOperativa && deviceOptions.length > 0 && (
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
            { label: "Estimación IA", value: `${estimationHours.toFixed(1)} h`, tip: isOperativa ? QC_OPERATIVA_ESTIMATION_TOOLTIP : QC_ESTIMATION_TOOLTIP },
            { label: "≈ Días QC", value: estimationDays.toFixed(1) },
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

      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Nombre</th>
            <th>Componente</th>
            <th>Ecosistema</th>
            <th>Dispositivo</th>
            <th>Prioridad</th>
            <th>Estado</th>
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
              <td>{testCase.test_case_id}</td>
              <td>{isOperativa ? stripDeviceFromCaseName(testCase.test_case_name, testCase.device) : testCase.test_case_name}</td>
              <td>{testCase.component}</td>
              <td>{testCase.ecosystem ?? "—"}</td>
              <td>{testCase.device ?? "—"}</td>
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
              <td colSpan={8} className="muted">
                {testCases.length === 0 ? "Sin test cases todavía." : "Ningún Test Case para ese dispositivo."}
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
