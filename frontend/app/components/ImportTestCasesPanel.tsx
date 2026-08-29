"use client";

import { AlertTriangle, FileSpreadsheet, Upload, X } from "lucide-react";
import { useRef, useState } from "react";
import { api, ApiRequestError } from "@/lib/api";
import type { BulkCreateResult, ImportPreviewResult, ImportSheetInfo } from "@/lib/types";

type Phase = "dropzone" | "analyzing" | "preview" | "importing" | "done";

const ACCEPTED_EXTENSIONS = [".xlsx", ".xlsm", ".csv"];

function isSpreadsheet(file: File): boolean {
  const name = file.name.toLowerCase();
  return name.endsWith(".xlsx") || name.endsWith(".xlsm");
}

export function ImportTestCasesPanel({
  releaseId,
  onClose,
  onImported,
}: {
  releaseId: number;
  onClose: () => void;
  onImported: () => void;
}): React.ReactElement {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [phase, setPhase] = useState<Phase>("dropzone");
  const [dragActive, setDragActive] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [sheets, setSheets] = useState<ImportSheetInfo[]>([]);
  const [selectedSheet, setSelectedSheet] = useState<string | null>(null);
  const [preview, setPreview] = useState<ImportPreviewResult | null>(null);
  const [importResult, setImportResult] = useState<BulkCreateResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runPreview = async (targetFile: File, sheetName: string | null): Promise<void> => {
    setPhase("analyzing");
    setError(null);
    try {
      const result = await api.previewImport(releaseId, targetFile, sheetName ?? undefined);
      setPreview(result);
      setSelectedSheet(result.sheet_name);
      setPhase("preview");
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "No se pudo analizar el archivo.");
      setPhase("dropzone");
    }
  };

  const handleFile = async (selected: File): Promise<void> => {
    setFile(selected);
    setError(null);

    if (!isSpreadsheet(selected)) {
      await runPreview(selected, null);
      return;
    }

    setPhase("analyzing");
    try {
      const sheetsResult = await api.listImportSheets(releaseId, selected);
      setSheets(sheetsResult.sheets);
      const recommended = sheetsResult.recommended_sheet;
      if (!recommended) {
        setError("No se detectó ninguna hoja con un formato reconocido en este archivo.");
        setPhase("dropzone");
        return;
      }
      await runPreview(selected, recommended);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "No se pudo leer el archivo.");
      setPhase("dropzone");
    }
  };

  const handleSheetChange = async (sheetName: string): Promise<void> => {
    if (!file) return;
    setSelectedSheet(sheetName);
    await runPreview(file, sheetName);
  };

  const handleDrop = (event: React.DragEvent<HTMLDivElement>): void => {
    event.preventDefault();
    setDragActive(false);
    const dropped = event.dataTransfer.files?.[0];
    if (dropped) void handleFile(dropped);
  };

  const handleConfirmImport = async (): Promise<void> => {
    if (!preview) return;
    setPhase("importing");
    setError(null);
    try {
      const result = await api.bulkCreateTestCases(releaseId, preview.valid);
      setImportResult(result);
      setPhase("done");
      onImported();
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "No se pudo importar.");
      setPhase("preview");
    }
  };

  const reset = (): void => {
    setPhase("dropzone");
    setFile(null);
    setSheets([]);
    setSelectedSheet(null);
    setPreview(null);
    setImportResult(null);
    setError(null);
  };

  return (
    <div className="panel import-panel">
      <div className="panel-header">
        <h2>Importar Test Cases</h2>
        <button type="button" className="icon-close" onClick={onClose} aria-label="Cerrar importador">
          <X size={16} />
        </button>
      </div>
      <div className="panel-body">
        {error && <p className="error-text">{error}</p>}

        {(phase === "dropzone" || phase === "analyzing") && (
          <div
            className={`dropzone${dragActive ? " active" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
            onDragLeave={() => setDragActive(false)}
            onDrop={handleDrop}
          >
            <Upload size={22} aria-hidden="true" />
            {phase === "analyzing" ? (
              <p>Analizando archivo…</p>
            ) : (
              <>
                <p>Arrastra tu archivo .xlsx o .csv aquí</p>
                <button type="button" className="secondary" onClick={() => fileInputRef.current?.click()}>
                  Seleccionar archivo
                </button>
              </>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPTED_EXTENSIONS.join(",")}
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
          <div className="import-preview">
            <div className="import-preview-meta">
              <span className="muted">
                <FileSpreadsheet size={13} aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: "4px" }} />
                {file?.name}
              </span>
              {sheets.length > 1 && (
                <select value={selectedSheet ?? ""} onChange={(e) => void handleSheetChange(e.target.value)}>
                  {sheets.map((s) => (
                    <option key={s.name} value={s.name} disabled={s.format === "UNKNOWN"}>
                      {s.name}{s.format === "UNKNOWN" ? " (no reconocida)" : ""}
                    </option>
                  ))}
                </select>
              )}
              <button type="button" className="secondary" onClick={reset}>Cambiar archivo</button>
            </div>

            <div className="import-stats">
              <div className="import-stat"><div className="import-stat-value">{preview.total_test_cases}</div><div className="import-stat-label">Detectados</div></div>
              <div className="import-stat ok"><div className="import-stat-value">{preview.valid_count}</div><div className="import-stat-label">Válidos</div></div>
              <div className="import-stat error"><div className="import-stat-value">{preview.error_count}</div><div className="import-stat-label">Con errores</div></div>
              <div className="import-stat warning"><div className="import-stat-value">{preview.warnings.length}</div><div className="import-stat-label">Advertencias</div></div>
            </div>

            {preview.warnings.length > 0 && (
              <div className="import-issues warning">
                <div className="import-issues-title"><AlertTriangle size={13} aria-hidden="true" /> Advertencias de calidad de datos</div>
                <ul>
                  {preview.warnings.slice(0, 8).map((w, i) => <li key={i}>{w.message}</li>)}
                  {preview.warnings.length > 8 && <li className="muted">+{preview.warnings.length - 8} más</li>}
                </ul>
              </div>
            )}

            {preview.errors.length > 0 && (
              <div className="import-issues error">
                <div className="import-issues-title"><AlertTriangle size={13} aria-hidden="true" /> Errores (no se importarán)</div>
                <ul>
                  {preview.errors.slice(0, 8).map((e, i) => <li key={i}>{e.message}</li>)}
                  {preview.errors.length > 8 && <li className="muted">+{preview.errors.length - 8} más</li>}
                </ul>
              </div>
            )}

            {preview.valid.length > 0 && (
              <table className="activity" style={{ marginTop: "10px" }}>
                <thead><tr><th>ID</th><th>Nombre</th><th>Prioridad</th><th>Steps</th></tr></thead>
                <tbody>
                  {preview.valid.slice(0, 5).map((tc) => (
                    <tr key={tc.test_case_id}>
                      <td>{tc.test_case_id}</td><td>{tc.test_case_name}</td><td className="muted">{tc.priority}</td><td className="muted">{tc.steps.length}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {preview.valid.length > 5 && <p className="muted" style={{ fontSize: "12px", marginTop: "6px" }}>+{preview.valid.length - 5} más…</p>}

            <div className="form-actions">
              <button type="button" onClick={handleConfirmImport} disabled={preview.valid_count === 0}>
                Importar {preview.valid_count} Test Case{preview.valid_count === 1 ? "" : "s"}
              </button>
              <button type="button" className="secondary" onClick={reset}>Cancelar</button>
            </div>
          </div>
        )}

        {phase === "importing" && <p className="muted">Importando…</p>}

        {phase === "done" && importResult && (
          <div className="import-preview">
            <div className="import-stats">
              <div className="import-stat ok"><div className="import-stat-value">{importResult.created.length}</div><div className="import-stat-label">Creados</div></div>
              <div className="import-stat error"><div className="import-stat-value">{importResult.errors.length}</div><div className="import-stat-label">Con errores</div></div>
            </div>
            {importResult.errors.length > 0 && (
              <div className="import-issues error">
                <div className="import-issues-title"><AlertTriangle size={13} aria-hidden="true" /> No se pudieron crear</div>
                <ul>{importResult.errors.map((e, i) => <li key={i}>{e.message}</li>)}</ul>
              </div>
            )}
            <div className="form-actions">
              <button type="button" onClick={onClose}>Listo</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
