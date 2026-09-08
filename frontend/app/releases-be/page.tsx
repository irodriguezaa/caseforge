"use client";

import { FileText, Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { StatusBadge } from "@/app/components/StatusBadge";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { BE_CLUSTER_OPTIONS, BE_CLUSTER_TODOS, BE_REGRESIVO_SCOPE_LABEL, BE_REGRESIVO_SCOPES, BE_SWF_OPTIONS } from "@/lib/constants";
import type { BeCluster, BeRegresivoScope, BeReleaseRead, BeReleaseUpdate } from "@/lib/types";

type RnSource = "with_rn" | "without_rn" | null;

export default function ReleaseBePage(): React.ReactElement {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();
  const { canLoadRn, canSeeDashboard } = useAuth();
  const editorRef = useRef<HTMLDivElement>(null);

  const [rnSource, setRnSource] = useState<RnSource>(null);
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [beRelease, setBeRelease] = useState<BeReleaseRead | null>(null);
  const [rows, setRows] = useState<BeReleaseRead[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const loadList = (): void => {
    setLoadingList(true);
    api
      .listBeReleases()
      .then(setRows)
      .catch((err: unknown) => setListError(err instanceof Error ? err.message : "Error"))
      .finally(() => setLoadingList(false));
  };

  useEffect(loadList, []);

  const resetDraft = (): void => {
    setBeRelease(null);
    setPdfFile(null);
    setAnalysisError(null);
    setCreateError(null);
  };

  const handleSourceChange = (source: RnSource): void => {
    setRnSource(source);
    resetDraft();
  };

  const handleFileSelect = (file: File): void => {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setAnalysisError("Solo se permiten archivos en formato PDF.");
      return;
    }
    setPdfFile(file);
    setAnalysisError(null);
    setCreateError(null);
    setBeRelease(null);
  };

  const handleAnalyze = async (): Promise<void> => {
    if (!pdfFile) return;
    setAnalyzing(true);
    setAnalysisError(null);
    try {
      const result = await api.analyzeBeRn(pdfFile);
      setBeRelease(result.be_release);
    } catch (err: unknown) {
      setAnalysisError(err instanceof Error ? err.message : "No se pudo analizar el RN de BE.");
    } finally {
      setAnalyzing(false);
    }
  };

  const handleContinueWithoutRn = async (): Promise<void> => {
    setStarting(true);
    setAnalysisError(null);
    try {
      const created = await api.createBeReleaseWithoutRn();
      setBeRelease(created);
    } catch (err: unknown) {
      setAnalysisError(err instanceof Error ? err.message : "No se pudo iniciar el Release BE.");
    } finally {
      setStarting(false);
    }
  };

  const patchRelease = async (payload: BeReleaseUpdate): Promise<boolean> => {
    if (!beRelease) return false;
    const previous = beRelease;
    setBeRelease({ ...beRelease, ...payload });
    setCreateError(null);
    try {
      const updated = await api.updateBeRelease(beRelease.id, payload);
      setBeRelease(updated);
      return true;
    } catch (err: unknown) {
      setBeRelease(previous);
      setCreateError(err instanceof Error ? err.message : "No se pudo guardar el Release BE.");
      return false;
    }
  };

  const toggleCluster = (option: BeCluster): void => {
    const current = (beRelease?.clusters ?? []) as BeCluster[];
    if (option === BE_CLUSTER_TODOS) {
      void patchRelease({ clusters: current.includes(BE_CLUSTER_TODOS) ? [] : [BE_CLUSTER_TODOS] });
      return;
    }
    const withoutTodos = current.filter((item) => item !== BE_CLUSTER_TODOS);
    const next: BeCluster[] = withoutTodos.includes(option)
      ? withoutTodos.filter((item) => item !== option)
      : [...withoutTodos, option];
    void patchRelease({ clusters: next });
  };

  const clusterLabel = (clusters: string[] | null | undefined): string =>
    clusters && clusters.length > 0 ? clusters.join(", ") : "—";

  const listedReleases = rows.filter((row) => row.qc_release_id);

  const handleRowClick = (row: BeReleaseRead): void => {
    if (!row.qc_release_id) {
      return;
    }
    router.push(`/releases/${row.qc_release_id}`);
  };

  const handleCreate = async (): Promise<void> => {
    if (!beRelease) return;
    const name = (beRelease.name ?? "").trim() || (beRelease.entregable ?? "").trim();
    const entregable = (beRelease.entregable ?? "").trim() || name;
    setCreating(true);
    setCreateError(null);
    try {
      const saved = await patchRelease({ name: name || null, entregable: entregable || null });
      if (!saved) {
        return;
      }
      if (!name) {
        setCreateError("El Nombre es obligatorio para crear el Release BE.");
        return;
      }
      const created = await api.createReleaseFromBe(beRelease.id);
      router.push(`/releases/${created.id}`);
    } catch (err: unknown) {
      setCreateError(err instanceof Error ? err.message : "No se pudo crear el Release BE.");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="page page-wide">
      <p className="eyebrow">Release BE</p>
      <h1>Regresivos de Backend</h1>
      <p className="subtitle">Fuente de información → datos → alcance → creación</p>

      {canLoadRn && (
      <>
      <div className="step-card">
        <div className="step-card-header">
          <h2>Paso 1. Fuente de información</h2>
        </div>
        <p className="muted" style={{ fontSize: "12px", margin: "0 0 12px" }}>
          El Release Note es opcional. Si no hay PDF, captura la información en el paso 2.
        </p>
        <div className="form-grid">
          <label className="form-field" style={{ flexDirection: "row", alignItems: "center", gap: "8px" }}>
            <input
              type="radio"
              name="be-rn-source"
              checked={rnSource === "with_rn"}
              onChange={() => handleSourceChange("with_rn")}
            />
            Sí, tengo Release Note
          </label>
          <label className="form-field" style={{ flexDirection: "row", alignItems: "center", gap: "8px" }}>
            <input
              type="radio"
              name="be-rn-source"
              checked={rnSource === "without_rn"}
              onChange={() => handleSourceChange("without_rn")}
            />
            No tengo Release Note
          </label>
        </div>

        {rnSource === "with_rn" && (
          <>
            <div
              className="dropzone"
              style={{ padding: "1.5rem 1rem", cursor: "pointer", marginTop: "12px" }}
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
                  <p style={{ margin: 0, fontWeight: 600 }}>Cargar RN en PDF</p>
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
            <div className="form-actions" style={{ marginTop: "12px" }}>
              <button
                type="button"
                className="secondary"
                disabled={mounted ? !pdfFile || analyzing : false}
                onClick={() => void handleAnalyze()}
              >
                <FileText size={14} style={{ verticalAlign: "-2px", marginRight: "6px" }} />
                {analyzing ? "Analizando RN…" : "Analizar RN"}
              </button>
            </div>
          </>
        )}

        {rnSource === "without_rn" && !beRelease && (
          <div className="form-actions" style={{ marginTop: "12px" }}>
            <button type="button" disabled={mounted ? starting : false} onClick={() => void handleContinueWithoutRn()}>
              {starting ? "Preparando…" : "Continuar sin Release Note"}
            </button>
          </div>
        )}

        {analysisError && <p className="error-text">{analysisError}</p>}
      </div>

      {beRelease && (
        <div className="step-card" key={`info-${beRelease.id}`} ref={editorRef}>
          <div className="step-card-header">
            <h2>Paso 2. Información del Release BE</h2>
            <span className="muted" style={{ fontSize: "12px" }}>
              Información cargada desde RN, se puede editar
            </span>
          </div>
          <div className="form-grid">
            <div className="form-field full">
              <label htmlFor="be-entregable">Entregable</label>
              <input
                id="be-entregable"
                placeholder="No disponible"
                value={beRelease.entregable ?? ""}
                onChange={(e) => setBeRelease({ ...beRelease, entregable: e.target.value || null })}
                onBlur={(e) => void patchRelease({ entregable: e.target.value.trim() || null })}
              />
            </div>
            <div className="form-field">
              <label htmlFor="be-name">Nombre</label>
              <input
                id="be-name"
                placeholder="No disponible"
                value={beRelease.name ?? ""}
                onChange={(e) => setBeRelease({ ...beRelease, name: e.target.value || null })}
                onBlur={(e) => void patchRelease({ name: e.target.value.trim() || null })}
              />
            </div>
            <div className="form-field full">
              <span id="be-swf-label">SWF solicitante</span>
              <div role="radiogroup" aria-labelledby="be-swf-label" className="choice-grid">
                {BE_SWF_OPTIONS.map((swf) => (
                  <label key={swf} className="choice-option">
                    <input
                      type="radio"
                      name="be-swf"
                      checked={beRelease.swf === swf}
                      onChange={() => void patchRelease({ swf })}
                    />
                    {swf}
                  </label>
                ))}
              </div>
            </div>
            <div className="form-field full">
              <span id="be-cluster-label">Cluster</span>
              <div role="group" aria-labelledby="be-cluster-label" className="choice-grid">
                {BE_CLUSTER_OPTIONS.map((cluster) => (
                  <label key={cluster} className="choice-option">
                    <input
                      type="checkbox"
                      name="be-cluster"
                      checked={(beRelease.clusters ?? []).includes(cluster)}
                      onChange={() => toggleCluster(cluster)}
                    />
                    {cluster}
                  </label>
                ))}
              </div>
            </div>
            <div className="form-field full">
              <label htmlFor="be-description">Descripción</label>
              <textarea
                id="be-description"
                placeholder="Notas sobre el alcance y componentes de este release"
                defaultValue={beRelease.description ?? ""}
                onBlur={(e) => void patchRelease({ description: e.target.value || null })}
              />
            </div>
          </div>
        </div>
      )}

      {beRelease && (
        <div className="step-card">
          <div className="step-card-header">
            <h2>Paso 3. Configuración</h2>
          </div>
          <div className="form-field">
            <label htmlFor="be-scope">Alcance de regresivo</label>
            <select
              id="be-scope"
              value={beRelease.regresivo_scope ?? ""}
              onChange={(e) =>
                void patchRelease({
                  regresivo_scope: (e.target.value || null) as BeRegresivoScope | null,
                })
              }
            >
              <option value="">Selecciona…</option>
              {BE_REGRESIVO_SCOPES.map((scope) => (
                <option key={scope} value={scope}>
                  {BE_REGRESIVO_SCOPE_LABEL[scope]}
                </option>
              ))}
            </select>
          </div>
          {beRelease.regresivo_scope === "ACOTADO" && (
            <div className="form-field full" style={{ marginTop: "12px" }}>
              <label htmlFor="be-component">Componente / Funcionalidad Afectada:</label>
              <textarea
                id="be-component"
                placeholder="Ej. Login, autenticación, playback, pagos..."
                defaultValue={beRelease.affected_component ?? ""}
                onBlur={(e) => void patchRelease({ affected_component: e.target.value || null })}
              />
            </div>
          )}
        </div>
      )}

      {createError && <p className="error-text">{createError}</p>}

      {beRelease && (
        <div className="step-card">
          <div className="step-card-header">
            <h2>Paso 4. Creación</h2>
          </div>
          <div className="form-actions">
            <button
              type="button"
              disabled={creating || !beRelease.swf}
              onClick={() => void handleCreate()}
            >
              {creating ? "Creando Release…" : "Crear Release"}
            </button>
          </div>
        </div>
      )}

      </>
      )}

      <div className="section-header">
        <h2>Listado de Release BE ({listedReleases.length})</h2>
      </div>
      {loadingList && <p className="muted">Cargando…</p>}
      {listError && <p className="error-text">{listError}</p>}
      {!loadingList && !listError && (
        <div className="panel">
          <table className="activity">
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Entregable</th>
                <th>SWF</th>
                <th>Cluster</th>
                <th>Alcance</th>
                <th>RN</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              {listedReleases.map((row) => (
                <tr
                  key={row.id}
                  className="clickable"
                  onClick={() => handleRowClick(row)}
                  title="Ver detalle de la Release"
                >
                  <td style={{ fontWeight: 500 }}>{row.name ?? "—"}</td>
                  <td className="muted">{row.entregable ?? "—"}</td>
                  <td className="muted">{row.swf ?? "—"}</td>
                  <td className="muted">{clusterLabel(row.clusters)}</td>
                  <td className="muted">
                    {row.regresivo_scope ? BE_REGRESIVO_SCOPE_LABEL[row.regresivo_scope] : "—"}
                  </td>
                  <td className="muted">{row.pdf_filename ?? "Sin RN"}</td>
                  <td>
                    {row.qc_release_status ? (
                      <StatusBadge status={row.qc_release_status} />
                    ) : (
                      <span className="muted">Pendiente</span>
                    )}
                  </td>
                </tr>
              ))}
              {listedReleases.length === 0 && (
                <tr>
                  <td colSpan={7} className="muted">
                    No hay Release BE todavía.
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
