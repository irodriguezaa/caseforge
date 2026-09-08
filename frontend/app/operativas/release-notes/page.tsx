"use client";

import { FileText, Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { OperativaEpcTable } from "@/app/components/OperativaEpcTable";
import { StatusBadge } from "@/app/components/StatusBadge";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { CLUSTERS } from "@/lib/constants";
import { calculateBusinessDays } from "@/lib/dateUtils";
import type { EpcUpdate, OperativaReleaseRead, OperativaReleaseUpdate } from "@/lib/types";

export default function OperativaReleaseNotesPage(): React.ReactElement {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();
  const { canLoadRn, canSeeDashboard } = useAuth();

  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [operativaRelease, setOperativaRelease] = useState<OperativaReleaseRead | null>(null);
  const [releases, setReleases] = useState<OperativaReleaseRead[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const editorRef = useRef<HTMLDivElement>(null);
  const entregableInputRef = useRef<HTMLInputElement>(null);

  // Defer native `disabled` until after hydrate. SSR + first client paint omit the
  // attribute (false). Applying disabled={true} on the first paint mismatches HTML
  // when an extension strips `disabled` from the server markup.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const loadReleases = (): void => {
    setLoadingList(true);
    api
      .listOperativaReleases()
      .then(setReleases)
      .catch((err: unknown) => setListError(err instanceof Error ? err.message : "Error"))
      .finally(() => setLoadingList(false));
  };

  useEffect(loadReleases, []);

  const handleFileSelect = (file: File): void => {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setAnalysisError("Solo se permiten archivos en formato PDF.");
      return;
    }
    setPdfFile(file);
    setAnalysisError(null);
    setCreateError(null);
    setOperativaRelease(null);
  };

  const handleAnalyze = async (): Promise<void> => {
    if (!pdfFile) return;
    setAnalyzing(true);
    setAnalysisError(null);
    try {
      const result = await api.analyzeOperativaRn(pdfFile);
      setOperativaRelease(result.operativa_release);
    } catch (err: unknown) {
      setAnalysisError(err instanceof Error ? err.message : "No se pudo analizar el RN Operativo.");
    } finally {
      setAnalyzing(false);
    }
  };

  const patchRelease = async (payload: OperativaReleaseUpdate): Promise<void> => {
    if (!operativaRelease) return;
    const previous = operativaRelease;
    setOperativaRelease({ ...operativaRelease, ...payload });
    try {
      const updated = await api.updateOperativaRelease(operativaRelease.id, payload);
      setOperativaRelease(updated);
    } catch (err: unknown) {
      setOperativaRelease(previous);
      setCreateError(err instanceof Error ? err.message : "No se pudo guardar la Operativa.");
    }
  };

  const patchEpc = async (epcId: number, payload: EpcUpdate): Promise<void> => {
    const updated = await api.updateEpc(epcId, payload);
    setOperativaRelease((prev) =>
      prev ? { ...prev, epcs: prev.epcs.map((e) => (e.id === updated.id ? updated : e)) } : prev
    );
  };

  const qcReleaseId = (row: OperativaReleaseRead): number | null =>
    row.qc_release_id ?? row.epcs.find((epc) => epc.release_id)?.release_id ?? null;

  const handleRowClick = async (row: OperativaReleaseRead): Promise<void> => {
    const releaseId = qcReleaseId(row);
    if (releaseId) {
      router.push(`/releases/${releaseId}`);
      return;
    }
    setCreateError(null);
    setAnalysisError(null);
    setPdfFile(null);
    try {
      let fresh = await api.getOperativaRelease(row.id);
      if (fresh.name && fresh.entregable !== fresh.name) {
        fresh = await api.updateOperativaRelease(fresh.id, { entregable: fresh.name });
      }
      setOperativaRelease(fresh);
    } catch {
      setOperativaRelease(row);
    }
    window.setTimeout(() => {
      editorRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 50);
  };

  const handleCreate = async (): Promise<void> => {
    if (!operativaRelease) return;
    setCreating(true);
    setCreateError(null);
    try {
      const created = await api.createReleaseFromOperativa(operativaRelease.id);
      router.push(`/releases/${created.id}`);
    } catch (err: unknown) {
      setCreateError(err instanceof Error ? err.message : "No se pudo crear el Release.");
    } finally {
      setCreating(false);
    }
  };

  const includedEpcs = operativaRelease?.epcs.filter((e) => e.include_in_qc) ?? [];
  const businessDays = calculateBusinessDays(
    operativaRelease?.start_date ?? "",
    operativaRelease?.end_date ?? ""
  );
  const clusterOptions =
    operativaRelease?.cluster && !(CLUSTERS as readonly string[]).includes(operativaRelease.cluster)
      ? [operativaRelease.cluster, ...CLUSTERS]
      : [...CLUSTERS];
  const jiraFilterValue = operativaRelease?.jira_filter_url ?? operativaRelease?.jira_filter_manual ?? "";

  return (
    <div className="page page-wide">
      <p className="eyebrow">Operativas</p>
      <h1>Release Notes Operativo</h1>
      <p className="subtitle">Carga → información del RN → configuración → análisis → creación</p>

      {canLoadRn && (
      <>
      <div className="step-card">
        <div className="step-card-header">
          <h2>Paso 1. Cargar RN Operativo</h2>
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
          ) : operativaRelease ? (
            <div>
              <p style={{ margin: 0, fontWeight: 600, color: "var(--text)" }}>
                {operativaRelease.pdf_filename}
              </p>
              <p className="muted" style={{ fontSize: "12px", margin: "4px 0 0" }}>
                RN ya analizado. Puedes seguir editando abajo o cargar otro PDF.
              </p>
            </div>
          ) : (
            <div>
              <p style={{ margin: 0, fontWeight: 600 }}>Cargar RN Operativo en PDF</p>
              <p className="muted" style={{ fontSize: "12px", margin: "4px 0 0" }}>
                Selecciona el archivo .pdf para extraer información del RN
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
            suppressHydrationWarning
            disabled={mounted ? !pdfFile || analyzing : false}
            onClick={handleAnalyze}
          >
            <FileText size={14} style={{ verticalAlign: "-2px", marginRight: "6px" }} />
            {analyzing ? "Analizando RN…" : "Analizar RN Operativo"}
          </button>
        </div>
      </div>

      {operativaRelease && (
        <div key={operativaRelease.id} ref={editorRef}>
        <div className="step-card">
          <div className="step-card-header">
            <h2>Paso 2. Información del RN</h2>
            <span className="muted" style={{ fontSize: "12px" }}>
              Información cargada desde RN, se puede editar
            </span>
          </div>
          <div className="form-grid">
            <div className="form-field full">
              <label htmlFor="entregable">Entregable</label>
              <input
                id="entregable"
                ref={entregableInputRef}
                placeholder="No disponible"
                defaultValue={operativaRelease.name ?? operativaRelease.entregable ?? ""}
                onBlur={(e) => void patchRelease({ entregable: e.target.value || null })}
              />
            </div>
            <div className="form-field">
              <label htmlFor="operativa-name">Nombre</label>
              <input
                id="operativa-name"
                placeholder="No disponible"
                defaultValue={operativaRelease.name ?? ""}
                onBlur={(e) => {
                  const name = e.target.value || null;
                  void patchRelease({ name, entregable: name });
                  if (entregableInputRef.current) {
                    entregableInputRef.current.value = e.target.value;
                  }
                }}
              />
            </div>
            <div className="form-field">
              <label htmlFor="operativa-cluster">Cluster</label>
              <select
                id="operativa-cluster"
                value={operativaRelease.cluster ?? ""}
                onChange={(e) => void patchRelease({ cluster: e.target.value || null })}
              >
                <option value="">No disponible</option>
                {clusterOptions.map((cluster) => (
                  <option key={cluster} value={cluster}>
                    {cluster}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-field full">
              <label htmlFor="operativa-description">Descripción</label>
              <textarea
                id="operativa-description"
                placeholder="Notas sobre el alcance y componentes de este release"
                defaultValue={operativaRelease.description ?? ""}
                onBlur={(e) => void patchRelease({ description: e.target.value || null })}
              />
            </div>
          </div>
        </div>

        <div className="step-card">
          <div className="step-card-header">
            <h2>Paso 3. Configuración</h2>
            <span className="muted" style={{ fontSize: "12px" }}>
              Parámetros operativos definidos por el usuario
            </span>
          </div>
          <div className="form-grid">
            <div className="form-field">
              <label htmlFor="operativa-start">Inicio de revisión</label>
              <input
                id="operativa-start"
                type="date"
                value={operativaRelease.start_date ?? ""}
                onChange={(e) => void patchRelease({ start_date: e.target.value || null })}
              />
            </div>
            <div className="form-field">
              <label htmlFor="operativa-end">Fin de revisión</label>
              <input
                id="operativa-end"
                type="date"
                min={operativaRelease.start_date ?? undefined}
                value={operativaRelease.end_date ?? ""}
                onChange={(e) => void patchRelease({ end_date: e.target.value || null })}
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
            <div className="form-field full">
              <label htmlFor="jira-filter">Filtro de issues Jira (URL / manual)</label>
              <input
                id="jira-filter"
                placeholder="https://dlatvarg.atlassian.net/issues/?filter=123456"
                defaultValue={jiraFilterValue}
                onBlur={(e) => void patchRelease({ jira_filter_url: e.target.value || null })}
              />
            </div>
            <div className="form-field full">
              <label htmlFor="instrucciones-adicionales">Instrucciones adicionales</label>
              <textarea
                id="instrucciones-adicionales"
                rows={3}
                placeholder="Notas para QC…"
                defaultValue={operativaRelease.instrucciones_adicionales ?? ""}
                onBlur={(e) =>
                  void patchRelease({ instrucciones_adicionales: e.target.value || null })
                }
              />
            </div>
          </div>
        </div>

        <div className="step-card">
          <div className="step-card-header">
            <h2>Paso 4. Análisis</h2>
          </div>
          <p className="muted" style={{ fontSize: "12px", margin: "0 0 12px" }}>
            La sugerencia es del sistema, la decisión es tuya — puedes cambiar &quot;Incluir en QC&quot; en
            cualquier momento, en cualquier dirección.
          </p>
          <OperativaEpcTable
            epcs={operativaRelease.epcs}
            onToggleInclude={(epc, includeInQc) => void patchEpc(epc.id, { include_in_qc: includeInQc })}
          />
        </div>

        {createError && <p className="error-text">{createError}</p>}

        <div className="step-card">
          <div className="step-card-header">
            <h2>Paso 5. Creación</h2>
          </div>
          <p className="muted" style={{ fontSize: "12px", margin: "0 0 12px" }}>
            Se creará un Release con los {includedEpcs.length} EPC(s) marcados para incluir.
            Esta selección queda congelada al crear; cambios posteriores en la Operativa no lo
            modifican.
          </p>
          <div className="form-actions">
            <button type="button" disabled={creating} onClick={() => void handleCreate()}>
              {creating ? "Creando Release…" : "Crear Release"}
            </button>
          </div>
        </div>
        </div>
      )}

      </>
      )}

      <div className="section-header">
        <h2>Listado de Releases ({releases.length})</h2>
      </div>

      {loadingList && <p className="muted">Cargando releases…</p>}
      {listError && <p className="error-text">{listError}</p>}

      {!loadingList && !listError && (
        <div className="panel">
          <table className="activity">
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Entregable</th>
                <th>Cluster</th>
                <th>BRF/TRIS en QC</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              {releases.map((row) => {
                const releaseId = qcReleaseId(row);
                return (
                <tr
                  key={row.id}
                  className="clickable"
                  onClick={() => void handleRowClick(row)}
                  title={releaseId ? "Ver detalle de la Release" : "Continuar edición de esta Operativa"}
                >
                  <td style={{ fontWeight: 500 }}>{row.name ?? "—"}</td>
                  <td className="muted">{row.entregable ?? "—"}</td>
                  <td className="muted">{row.cluster ?? "—"}</td>
                  <td>{row.epcs.filter((e) => e.include_in_qc).length}</td>
                  <td>
                    {row.qc_release_status ? (
                      <StatusBadge status={row.qc_release_status} />
                    ) : (
                      <span className="muted">Pendiente</span>
                    )}
                  </td>
                </tr>
                );
              })}
              {releases.length === 0 && (
                <tr>
                  <td colSpan={5} className="muted">
                    No hay releases todavía.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {canSeeDashboard && (
        <p style={{ marginTop: "1.5rem" }}>
          <Link href="/" className="back-link">
            ← Volver al Dashboard
          </Link>
        </p>
      )}
    </div>
  );
}
