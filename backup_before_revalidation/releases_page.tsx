"use client";

import { FileText, Sparkles, Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ReleaseAnalysisCard } from "@/app/components/ReleaseAnalysisCard";
import { StatusBadge } from "@/app/components/StatusBadge";
import { api, ApiRequestError } from "@/lib/api";
import { DEVICE_OPTIONS, RELEASE_CLUSTER_OPTIONS, VALIDATION_TYPE_OPTIONS } from "@/lib/constants";
import { calculateBusinessDays } from "@/lib/dateUtils";
import type { ReleaseAnalysis, ReleaseWithCounts } from "@/lib/types";

const emptyForm = {
  name: "",
  version: "",
  platform: "WIN/XBOX",
  cluster: "Todos",
  description: "",
  startDate: "",
  endDate: "",
  qcResources: 1,
  validationType: "Smoke",
  jiraIssueFilter: "",
};

export default function ReleasesPage(): React.ReactElement {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [releases, setReleases] = useState<ReleaseWithCounts[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Form State
  const [form, setForm] = useState(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // PDF Upload & Analysis State
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [analysisResult, setAnalysisResult] = useState<ReleaseAnalysis | null>(null);
  const [generateMessage, setGenerateMessage] = useState<string | null>(null);

  const loadReleases = (): void => {
    setLoading(true);
    api
      .listReleases()
      .then(setReleases)
      .catch((err: unknown) => setLoadError(err instanceof Error ? err.message : "Error"))
      .finally(() => setLoading(false));
  };

  useEffect(loadReleases, []);

  // Calculate business days dynamically
  const businessDays = calculateBusinessDays(form.startDate, form.endDate);

  const handleFileSelect = (file: File): void => {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setAnalysisError("Solo se permiten archivos en formato PDF.");
      return;
    }
    setPdfFile(file);
    setAnalysisError(null);
    setAnalysisResult(null);
    setGenerateMessage(null);
  };

  const handleAnalyzePdf = async (): Promise<void> => {
    if (!pdfFile) return;
    setAnalyzing(true);
    setAnalysisError(null);
    setGenerateMessage(null);
    try {
      const response = await api.analyzeReleaseNote(pdfFile);
      const analysis = response.analysis;
      setAnalysisResult(analysis);

      // Populate extracted metadata without overwriting user-provided operational inputs
      setForm((prev) => ({
        ...prev,
        name: analysis.detected_name || prev.name,
        version: analysis.detected_version || prev.version,
        platform: analysis.detected_platform && DEVICE_OPTIONS.includes(analysis.detected_platform as any)
          ? analysis.detected_platform
          : prev.platform,
        description: analysis.detected_description || prev.description,
      }));
    } catch (err) {
      setAnalysisError(err instanceof ApiRequestError ? err.message : "No se pudo analizar el archivo PDF.");
    } finally {
      setAnalyzing(false);
    }
  };

  const handleGenerateClick = (): void => {
    setGenerateMessage(
      "Flujo de generación preparado. El motor QC basado en reglas .md se integrará en la siguiente fase para generar automáticamente los casos en esta Release."
    );
  };

  const handleSubmit = async (event: React.FormEvent): Promise<void> => {
    event.preventDefault();
    setSubmitting(true);
    setFormError(null);
    try {
      const created = await api.createRelease({
        name: form.name,
        version: form.version,
        platform: form.platform,
        cluster: form.cluster || null,
        description: form.description || null,
        start_date: form.startDate || null,
        end_date: form.endDate || null,
        qc_resources: form.qcResources ? Number(form.qcResources) : null,
        execution_days: businessDays,
        validation_type: form.validationType,
        jira_issue_filter: form.jiraIssueFilter || null,
        analysis_data: analysisResult || undefined,
      });

      // Also create an initial ReleaseWindow if dates were provided
      if (form.startDate && form.endDate) {
        try {
          await api.createReleaseWindow(created.id, {
            name: "Ventana inicial",
            start_date: form.startDate,
            end_date: form.endDate,
            status: "ACTIVE",
          });
        } catch {
          // Non-blocking for the release creation
        }
      }

      setForm(emptyForm);
      setPdfFile(null);
      setAnalysisResult(null);
      router.push(`/releases/${created.id}`);
    } catch (err) {
      setFormError(err instanceof ApiRequestError ? err.message : "No se pudo crear la release.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="page page-wide">
      <p className="eyebrow">CaseForge</p>
      <h1>Release</h1>
      <p className="subtitle">Gestión de releases y ciclo de calidad QC</p>

      {/* Structured 5-Block Creation Form */}
      <form onSubmit={handleSubmit} style={{ marginTop: "1.5rem" }}>
        
        {/* BLOQUE 1: Release Note PDF */}
        <div className="step-card">
          <div className="step-card-header">
            <h2>
              <span className="step-number-badge">1</span>
              Release Note
            </h2>
            {pdfFile && (
              <span className="badge badge-info" style={{ fontSize: "11px" }}>
                {pdfFile.name} ({(pdfFile.size / 1024).toFixed(1)} KB)
              </span>
            )}
          </div>

          <div
            className="dropzone"
            style={{ padding: "1.5rem 1rem", cursor: "pointer" }}
            onClick={() => fileInputRef.current?.click()}
          >
            <Upload size={22} aria-hidden="true" style={{ color: "var(--accent)" }} />
            {pdfFile ? (
              <div>
                <p style={{ margin: 0, fontWeight: 600, color: "var(--text)" }}>{pdfFile.name}</p>
                <p className="muted" style={{ fontSize: "12px", margin: "4px 0 0" }}>
                  Listo para analizar. Haz clic para cambiar el archivo.
                </p>
              </div>
            ) : (
              <div>
                <p style={{ margin: 0, fontWeight: 600 }}>Cargar Release Note en PDF</p>
                <p className="muted" style={{ fontSize: "12px", margin: "4px 0 0" }}>
                  Selecciona el archivo .pdf para extraer información de la release
                </p>
              </div>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf"
              style={{ display: "none" }}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleFileSelect(file);
                e.target.value = "";
              }}
            />
          </div>

          {analysisError && <p className="error-text">{analysisError}</p>}

          <div className="form-actions" style={{ marginTop: "12px" }}>
            <button
              type="button"
              className="secondary"
              disabled={!pdfFile || analyzing}
              onClick={handleAnalyzePdf}
            >
              <FileText size={14} style={{ verticalAlign: "-2px", marginRight: "6px" }} />
              {analyzing ? "Analizando Release Note…" : "Analizar Release Note"}
            </button>
          </div>
        </div>

        {/* BLOQUE 2: Información de la Release */}
        <div className="step-card">
          <div className="step-card-header">
            <h2>
              <span className="step-number-badge">2</span>
              Información de la Release
            </h2>
            <span className="muted" style={{ fontSize: "12px" }}>Campos extraídos / editables</span>
          </div>
          <div className="form-grid">
            <div className="form-field">
              <label htmlFor="name">Nombre</label>
              <input
                id="name"
                required
                placeholder="CV - WINDOWS/XBOX"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </div>
            <div className="form-field">
              <label htmlFor="version">Versión</label>
              <input
                id="version"
                required
                placeholder="7.8.1"
                value={form.version}
                onChange={(e) => setForm({ ...form, version: e.target.value })}
              />
            </div>
            <div className="form-field">
              <label htmlFor="platform">Dispositivo</label>
              <select
                id="platform"
                required
                value={form.platform}
                onChange={(e) => setForm({ ...form, platform: e.target.value })}
              >
                {DEVICE_OPTIONS.map((dev) => (
                  <option key={dev} value={dev}>
                    {dev}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-field full">
              <label htmlFor="description">Descripción</label>
              <textarea
                id="description"
                placeholder="Notas sobre el alcance y componentes de esta release"
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
              />
            </div>
          </div>
        </div>

        {/* BLOQUE 3: Configuración QC */}
        <div className="step-card">
          <div className="step-card-header">
            <h2>
              <span className="step-number-badge">3</span>
              Configuración QC
            </h2>
            <span className="muted" style={{ fontSize: "12px" }}>Parámetros operativos definidos por el usuario</span>
          </div>
          <div className="form-grid">
            <div className="form-field">
              <label htmlFor="cluster">Clúster</label>
              <select
                id="cluster"
                required
                value={form.cluster}
                onChange={(e) => setForm({ ...form, cluster: e.target.value })}
              >
                {RELEASE_CLUSTER_OPTIONS.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-field">
              <label htmlFor="startDate">Inicio de revisión</label>
              <input
                id="startDate"
                type="date"
                value={form.startDate}
                onChange={(e) => setForm({ ...form, startDate: e.target.value })}
              />
            </div>
            <div className="form-field">
              <label htmlFor="endDate">Fin de revisión</label>
              <input
                id="endDate"
                type="date"
                min={form.startDate || undefined}
                value={form.endDate}
                onChange={(e) => setForm({ ...form, endDate: e.target.value })}
              />
            </div>
            <div className="form-field">
              <label>Días de ejecución (hábiles)</label>
              <div
                style={{
                  background: "var(--surface-2)",
                  border: "1px solid var(--border-strong)",
                  borderRadius: "7px",
                  padding: ".55rem .7rem",
                  fontWeight: 600,
                  color: businessDays > 0 ? "var(--accent)" : "var(--text-dim)",
                }}
              >
                {businessDays > 0 ? `${businessDays} día${businessDays > 1 ? "s" : ""}` : "—"}
              </div>
            </div>
            <div className="form-field">
              <label htmlFor="qcResources">Recursos QC</label>
              <input
                id="qcResources"
                type="number"
                min={1}
                max={50}
                value={form.qcResources}
                onChange={(e) => setForm({ ...form, qcResources: Number(e.target.value) || 1 })}
              />
            </div>
            <div className="form-field">
              <label htmlFor="validationType">Regresivo (Tipo de validación)</label>
              <select
                id="validationType"
                value={form.validationType}
                onChange={(e) => setForm({ ...form, validationType: e.target.value })}
              >
                {VALIDATION_TYPE_OPTIONS.map((vt) => (
                  <option key={vt} value={vt}>
                    {vt}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-field full">
              <label htmlFor="jiraIssueFilter">Filtro de issues (Jira)</label>
              <input
                id="jiraIssueFilter"
                placeholder="project = CV AND fixVersion = 7.8.1"
                value={form.jiraIssueFilter}
                onChange={(e) => setForm({ ...form, jiraIssueFilter: e.target.value })}
              />
            </div>
          </div>
        </div>

        {/* BLOQUE 4: Resultados del Análisis (si existe análisis) */}
        {analysisResult && (
          <div className="step-card" style={{ padding: 0, border: "none", background: "transparent" }}>
            <ReleaseAnalysisCard
              analysis={analysisResult}
              qcResources={form.qcResources}
              executionDays={businessDays}
              onGenerateClick={handleGenerateClick}
            />
          </div>
        )}

        {generateMessage && (
          <div className="import-issues warning" style={{ marginTop: "10px" }}>
            <div className="import-issues-title">
              <Sparkles size={14} aria-hidden="true" />
              Preparación de Generación
            </div>
            <p style={{ margin: 0 }}>{generateMessage}</p>
          </div>
        )}

        {formError && <p className="error-text">{formError}</p>}

        {/* BLOQUE 5: Acciones y Creación */}
        <div className="form-actions" style={{ marginTop: "1.25rem", marginBottom: "2rem" }}>
          <button type="submit" disabled={submitting}>
            {submitting ? "Creando Release…" : "Crear Release"}
          </button>
        </div>
      </form>

      {/* Listado de Releases existentes */}
      <div className="section-header">
        <h2>Listado de Releases ({releases.length})</h2>
      </div>

      {loading && <p className="muted">Cargando releases…</p>}
      {loadError && <p className="error-text">{loadError}</p>}

      {!loading && !loadError && (
        <div className="panel">
          <table className="activity">
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Versión</th>
                <th>Dispositivo</th>
                <th>Cluster</th>
                <th>Estado</th>
                <th>Test Cases</th>
              </tr>
            </thead>
            <tbody>
              {releases.map((release) => (
                <tr
                  key={release.id}
                  className="clickable"
                  onClick={() => router.push(`/releases/${release.id}`)}
                >
                  <td style={{ fontWeight: 500 }}>{release.name}</td>
                  <td className="muted">v{release.version}</td>
                  <td className="muted">{release.platform}</td>
                  <td className="muted">{release.cluster ?? "—"}</td>
                  <td><StatusBadge status={release.status} /></td>
                  <td>{release.test_case_count}</td>
                </tr>
              ))}
              {releases.length === 0 && (
                <tr>
                  <td colSpan={6} className="muted">
                    No hay releases todavía.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      <p style={{ marginTop: "1.5rem" }}>
        <Link href="/" className="back-link">
          ← Volver al Dashboard
        </Link>
      </p>
    </div>
  );
}
