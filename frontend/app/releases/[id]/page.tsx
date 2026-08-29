"use client";

import { Eye, FileText, Plus, Sparkles, Upload } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ImportTestCasesPanel } from "@/app/components/ImportTestCasesPanel";
import { ReleaseAnalysisModal } from "@/app/components/ReleaseAnalysisModal";
import { StatusBadge } from "@/app/components/StatusBadge";
import { api, ApiRequestError } from "@/lib/api";
import type { Release, ReleaseAnalysis, ReleaseStatus, TestCase } from "@/lib/types";

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

  const [release, setRelease] = useState<Release | null>(null);
  const [analysis, setAnalysis] = useState<ReleaseAnalysis | null>(null);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [submitting, setSubmitting] = useState(false);

  const [showImport, setShowImport] = useState(false);
  const [showManualForm, setShowManualForm] = useState(false);
  const [showAnalysisModal, setShowAnalysisModal] = useState(false);
  const [generateFeedback, setGenerateFeedback] = useState<string | null>(null);

  const load = (): void => {
    setLoadError(null);
    Promise.all([
      api.getRelease(releaseId),
      api.listTestCases(releaseId),
      api.getReleaseAnalysis(releaseId).catch(() => null),
    ])
      .then(([releaseData, testCaseData, analysisData]) => {
        setRelease(releaseData);
        setTestCases(testCaseData);
        setAnalysis(analysisData);
      })
      .catch((err: unknown) => setLoadError(err instanceof Error ? err.message : "Error"));
  };

  useEffect(load, [releaseId]);

  const handleStatusChange = async (status: ReleaseStatus): Promise<void> => {
    setActionError(null);
    try {
      const updated = await api.updateRelease(releaseId, { status });
      setRelease(updated);
    } catch (err) {
      setActionError(err instanceof ApiRequestError ? err.message : "No se pudo actualizar el estado.");
    }
  };

  const handleDelete = async (): Promise<void> => {
    setActionError(null);
    try {
      await api.deleteRelease(releaseId);
      router.push("/releases");
    } catch (err) {
      setActionError(err instanceof ApiRequestError ? err.message : "No se pudo eliminar la release.");
    }
  };

  const handleGenerateCases = async (): Promise<void> => {
    setActionError(null);
    setGenerateFeedback(null);
    try {
      const res = await api.generateCasesFromRN(releaseId);
      setGenerateFeedback(
        `${res.message} (Regresivo: ${res.validation_type}, Estado: ${res.status})`
      );
    } catch (err) {
      setActionError(err instanceof ApiRequestError ? err.message : "No se pudo ejecutar la preparación de generación.");
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

  if (loadError) {
    return (
      <div className="page">
        <p className="error-text">{loadError}</p>
        <Link href="/releases" className="back-link">← Volver a Releases</Link>
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

  const canDelete = release.status === "DRAFT";

  return (
    <div className="page page-wide">
      <p style={{ marginBottom: "1rem" }}>
        <Link href="/releases" className="back-link">← Volver a Releases</Link>
      </p>
      <p className="eyebrow">Release</p>
      <h1>
        {release.name} <span className="muted">v{release.version}</span>
      </h1>
      <p className="subtitle">
        {release.platform}
        {release.cluster ? ` · ${release.cluster}` : ""} · <StatusBadge status={release.status} />
      </p>

      {/* QC Configuration & Operational Meta Card */}
      <div className="card" style={{ marginTop: "1rem" }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "12px", fontSize: "12.5px" }}>
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
          <div>
            <span className="muted" style={{ display: "block", fontSize: "11px", textTransform: "uppercase" }}>Recursos QC</span>
            <span style={{ fontWeight: 600 }}>{release.qc_resources ?? 1} recurso(s)</span>
          </div>
          <div>
            <span className="muted" style={{ display: "block", fontSize: "11px", textTransform: "uppercase" }}>Tipo de validación</span>
            <span style={{ fontWeight: 600 }}>{release.validation_type ?? "Smoke"}</span>
          </div>
          {release.jira_issue_filter && (
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

      {actionError && <p className="error-text">{actionError}</p>}
      {generateFeedback && (
        <div className="import-issues warning" style={{ marginTop: "10px" }}>
          <div className="import-issues-title">
            <Sparkles size={14} aria-hidden="true" />
            Estado del Motor QC
          </div>
          <p style={{ margin: 0 }}>{generateFeedback}</p>
        </div>
      )}

      {/* Lifecycle Actions */}
      <div className="card">
        <h2>Acciones de Ciclo de Vida</h2>
        <div className="form-actions">
          {(NEXT_STATUS[release.status] ?? []).map((next) => (
            <button key={next} type="button" onClick={() => handleStatusChange(next)}>
              Mover a {next}
            </button>
          ))}
          {analysis && (
            <button type="button" className="secondary" onClick={() => setShowAnalysisModal(true)}>
              <FileText size={14} style={{ verticalAlign: "-2px", marginRight: "6px" }} />
              Ver análisis de Release Note
            </button>
          )}
          <button
            type="button"
            className="danger"
            disabled={!canDelete}
            title={canDelete ? undefined : "Solo se pueden eliminar releases en DRAFT. Usa CANCELLED."}
            onClick={handleDelete}
          >
            Eliminar
          </button>
        </div>
        {!canDelete && (
          <p className="muted" style={{ marginTop: ".75rem" }}>
            Esta release ya tiene actividad: solo puede moverse a CANCELLED, no eliminarse.
          </p>
        )}
      </div>

      {/* Test Cases Section */}
      <div className="section-header">
        <h2>Test Cases ({testCases.length})</h2>
        <div className="form-actions" style={{ margin: 0 }}>
          <button
            type="button"
            onClick={handleGenerateCases}
            style={{ background: "var(--accent-dim)", color: "#a9c8fb", border: "1px solid var(--accent)" }}
          >
            <Sparkles size={14} aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: "6px" }} />
            Generar casos desde RN
          </button>
          <button type="button" onClick={() => { setShowImport((v) => !v); setShowManualForm(false); }}>
            <Upload size={14} aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: "6px" }} />
            Importar Test Cases
          </button>
          <button type="button" className="secondary" onClick={() => { setShowManualForm((v) => !v); setShowImport(false); }}>
            <Plus size={14} aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: "6px" }} />
            Nuevo Test Case
          </button>
        </div>
      </div>

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
            Alta manual — para cargas masivas usa &quot;Importar Test Cases&quot; o &quot;Generar casos desde RN&quot;.
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
            <th>Prioridad</th>
            <th>Estado</th>
          </tr>
        </thead>
        <tbody>
          {testCases.map((testCase) => (
            <tr
              key={testCase.id}
              className="clickable"
              onClick={() => router.push(`/test-cases/${testCase.id}`)}
            >
              <td>{testCase.test_case_id}</td>
              <td>{testCase.test_case_name}</td>
              <td>{testCase.component}</td>
              <td>{testCase.priority}</td>
              <td onClick={(e) => e.stopPropagation()}>
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
              </td>
            </tr>
          ))}
          {testCases.length === 0 && (
            <tr>
              <td colSpan={5} className="muted">
                Sin test cases todavía.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {showAnalysisModal && analysis && (
        <ReleaseAnalysisModal analysis={analysis} onClose={() => setShowAnalysisModal(false)} />
      )}

      <p style={{ marginTop: "1.5rem" }}>
        <Link href="/releases" className="back-link">← Volver a Releases</Link>
      </p>
    </div>
  );
}
