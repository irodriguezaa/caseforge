"use client";

import { AlertTriangle, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { api, ApiRequestError } from "@/lib/api";
import type { QcTicketBulkCreateResult, QcTicketImportPreviewResult, QcTicketSource, QcTicketView } from "@/lib/types";

type Phase = "idle" | "analyzing" | "preview" | "importing" | "done";

export function QcTicketUploadCard({
  title,
  filterTag,
  view,
  source,
  onImported,
}: {
  title: string;
  filterTag?: string;
  view: QcTicketView;
  source: QcTicketSource;
  onImported: () => void;
}): React.ReactElement {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [dragActive, setDragActive] = useState(false);
  const [preview, setPreview] = useState<QcTicketImportPreviewResult | null>(null);
  const [result, setResult] = useState<QcTicketBulkCreateResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleFile = async (file: File): Promise<void> => {
    setPhase("analyzing");
    setError(null);
    try {
      const preview = await api.previewQcTicketImport(file, view, source);
      setPreview(preview);
      setPhase("preview");
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "No se pudo analizar el archivo.");
      setPhase("idle");
    }
  };

  const handleConfirm = async (): Promise<void> => {
    if (!preview) return;
    setPhase("importing");
    setError(null);
    try {
      const result = await api.bulkCreateQcTickets(preview.valid);
      setResult(result);
      setPhase("done");
      onImported();
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "No se pudo importar.");
      setPhase("preview");
    }
  };

  const reset = (): void => {
    setPhase("idle");
    setPreview(null);
    setResult(null);
    setError(null);
  };

  return (
    <div className="panel">
      <div className="panel-header">
        <div className="upload-card-header" style={{ width: "100%" }}>
          <h2>{title}</h2>
          {filterTag && <span className="upload-filter-tag">{filterTag}</span>}
        </div>
      </div>
      <div className="panel-body">
        {error && <p className="error-text">{error}</p>}

        {(phase === "idle" || phase === "analyzing") && (
          <div
            className={`dropzone${dragActive ? " active" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
            onDragLeave={() => setDragActive(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragActive(false);
              const dropped = e.dataTransfer.files?.[0];
              if (dropped) void handleFile(dropped);
            }}
          >
            <Upload size={20} aria-hidden="true" />
            {phase === "analyzing" ? (
              <p>Analizando…</p>
            ) : (
              <>
                <p className="muted" style={{ fontSize: "12.5px" }}>Export de Jira (.csv o .xlsx)</p>
                <button type="button" className="secondary" onClick={() => fileInputRef.current?.click()}>
                  Seleccionar archivo
                </button>
              </>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.xlsx,.xlsm"
              style={{ display: "none" }}
              onChange={(e) => {
                const selected = e.target.files?.[0];
                if (selected) void handleFile(selected);
                e.target.value = "";
              }}
            />
          </div>
        )}

        {phase === "preview" && preview && (
          <>
            <div className="import-stats">
              <div className="import-stat"><div className="import-stat-value">{preview.total_rows}</div><div className="import-stat-label">Detectados</div></div>
              <div className="import-stat ok"><div className="import-stat-value">{preview.valid_count}</div><div className="import-stat-label">Válidos</div></div>
              <div className="import-stat error"><div className="import-stat-value">{preview.error_count}</div><div className="import-stat-label">Con errores</div></div>
              <div className="import-stat warning"><div className="import-stat-value">{preview.warnings.length}</div><div className="import-stat-label">Advertencias</div></div>
            </div>
            {preview.excluded_cancelled_count > 0 && (
              <p className="muted" style={{ fontSize: "12.5px" }}>
                {preview.excluded_cancelled_count} cancelado(s) excluido(s) automáticamente (no cuentan en ningún conteo).
              </p>
            )}
            {preview.warnings.length > 0 && (
              <div className="import-issues warning">
                <div className="import-issues-title"><AlertTriangle size={13} aria-hidden="true" /> Advertencias</div>
                <ul>
                  {preview.warnings.slice(0, 6).map((w, i) => <li key={i}>{w.message}</li>)}
                  {preview.warnings.length > 6 && <li className="muted">+{preview.warnings.length - 6} más</li>}
                </ul>
              </div>
            )}
            {preview.errors.length > 0 && (
              <div className="import-issues error">
                <div className="import-issues-title"><AlertTriangle size={13} aria-hidden="true" /> Errores</div>
                <ul>
                  {preview.errors.slice(0, 6).map((e, i) => <li key={i}>{e.message}</li>)}
                  {preview.errors.length > 6 && <li className="muted">+{preview.errors.length - 6} más</li>}
                </ul>
              </div>
            )}
            <div className="form-actions">
              <button type="button" onClick={handleConfirm} disabled={preview.valid_count === 0}>
                Importar {preview.valid_count}
              </button>
              <button type="button" className="secondary" onClick={reset}>Cancelar</button>
            </div>
          </>
        )}

        {phase === "importing" && <p className="muted">Importando…</p>}

        {phase === "done" && result && (
          <>
            <div className="import-stats">
              <div className="import-stat ok"><div className="import-stat-value">{result.created.length}</div><div className="import-stat-label">Creados</div></div>
              <div className="import-stat error"><div className="import-stat-value">{result.errors.length}</div><div className="import-stat-label">Con errores</div></div>
            </div>
            <div className="form-actions">
              <button type="button" onClick={reset}>Cargar otro archivo</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
