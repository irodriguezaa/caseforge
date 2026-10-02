"use client";

import { useState } from "react";
import { api, ApiRequestError } from "@/lib/api";
import type { ReleaseAnalysis } from "@/lib/types";

interface ReleaseAnalysisCardProps {
  analysis: ReleaseAnalysis;
  qcResources?: number | null;
  executionDays?: number | null;
  effortHours?: number | null;
  personDays?: number | null;
  durationDays?: number | null;
  releaseId?: number | null;
}

export function ReleaseAnalysisCard({
  analysis,
  qcResources,
  executionDays,
  effortHours,
  personDays,
  durationDays,
  releaseId,
}: ReleaseAnalysisCardProps): React.ReactElement {
  const hasWindow = executionDays !== undefined && executionDays !== null && executionDays > 0;
  const hasEffort = effortHours !== undefined && effortHours !== null;
  const testers = qcResources ?? 1;
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const canExtract =
    (releaseId != null && releaseId > 0) || Boolean(analysis.pdf_file_path);

  async function handleExtractScope(): Promise<void> {
    if (!canExtract || exporting) {
      return;
    }
    setExporting(true);
    setExportError(null);
    try {
      await api.exportRnScope({
        releaseId: releaseId ?? undefined,
        pdfFilePath: analysis.pdf_file_path,
        filename: analysis.pdf_filename,
        downloadName: analysis.detected_name || analysis.pdf_filename || "RN",
      });
    } catch (err) {
      setExportError(
        err instanceof ApiRequestError ? err.message : "No se pudo extraer el alcance del RN.",
      );
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="card" style={{ borderLeft: "3px solid var(--accent)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
          <h2>Análisis de Release</h2>
          <span className="badge badge-info" style={{ fontSize: "11px" }}>
            QC Engine: {analysis.qc_engine_version}
          </span>
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))",
            gap: "10px",
          }}
        >
          {[
            { label: "Funcionalidades", value: analysis.features_count },
            { label: "NCOS", value: analysis.nco_issues_count },
            { label: "QA/QC Bugs", value: analysis.qa_qc_issues_count },
            { label: "TRIS", value: analysis.tri_issues_count },
          ].map((stat) => (
            <div
              key={stat.label}
              style={{
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
                padding: "10px 14px",
                borderRadius: "8px",
              }}
            >
              <div style={{ fontSize: "10.5px", textTransform: "uppercase", letterSpacing: ".04em", color: "var(--text-dim)" }}>
                {stat.label}
              </div>
              <div style={{ fontSize: "22px", fontWeight: 700, marginTop: "2px" }}>{stat.value}</div>
            </div>
          ))}
        </div>

        {(hasWindow || hasEffort) && (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
              gap: "10px",
              marginTop: "12px",
            }}
          >
            {[
              {
                label: "Ventana de ejecución",
                value: hasWindow ? `${executionDays} días hábiles` : "—",
              },
              {
                label: "Esfuerzo estimado QC",
                value: hasEffort ? `${Number(effortHours).toFixed(1)} h` : "—",
              },
              {
                label: "Duración estimada",
                value: durationDays != null ? `${Number(durationDays).toFixed(1)} días` : "—",
              },
              {
                label: "Recursos QC",
                value: String(testers),
              },
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
                </div>
                <div style={{ fontSize: "16px", fontWeight: 700, marginTop: "2px" }}>{stat.value}</div>
              </div>
            ))}
          </div>
        )}
        {personDays != null && hasEffort ? (
          <p className="muted" style={{ fontSize: "12.5px", margin: "14px 0 0" }}>
            Días-persona: {Number(personDays).toFixed(1)} (jornada de 6 h). La ventana de ejecución es el calendario startDate → endDate y no se calcula con el esfuerzo.
          </p>
        ) : null}
        <div style={{ marginTop: "14px" }}>
          <button type="button" onClick={() => void handleExtractScope()} disabled={!canExtract || exporting}>
            {exporting ? "Extrayendo…" : "Extraer alcance RN"}
          </button>
          {exportError ? <p className="error-text" style={{ margin: "8px 0 0" }}>{exportError}</p> : null}
        </div>
      </div>
  );
}
