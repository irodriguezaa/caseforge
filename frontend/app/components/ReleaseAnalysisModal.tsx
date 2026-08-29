"use client";

import { AlertTriangle, CheckCircle2, FileText, X } from "lucide-react";
import type { ReleaseAnalysis } from "@/lib/types";

interface ReleaseAnalysisModalProps {
  analysis: ReleaseAnalysis;
  onClose: () => void;
}

export function ReleaseAnalysisModal({
  analysis,
  onClose,
}: ReleaseAnalysisModalProps): React.ReactElement {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>
            <FileText size={18} style={{ verticalAlign: "-3px", marginRight: "8px", color: "var(--accent)" }} />
            Análisis de Release Note — {analysis.pdf_filename}
          </h2>
          <button type="button" className="icon-close" onClick={onClose} aria-label="Cerrar">
            <X size={18} />
          </button>
        </div>

        <div className="modal-body">
          <div className="analysis-stat-grid">
            <div className="analysis-stat-cell">
              <div className="analysis-stat-num">{analysis.features_count}</div>
              <div className="analysis-stat-lbl">Funcionalidades</div>
            </div>
            <div className="analysis-stat-cell">
              <div className="analysis-stat-num">{analysis.qa_qc_issues_count}</div>
              <div className="analysis-stat-lbl">Incidencias QA/QC</div>
            </div>
            <div className="analysis-stat-cell">
              <div className="analysis-stat-num">{analysis.nco_issues_count}</div>
              <div className="analysis-stat-lbl">Incidencias NCO</div>
            </div>
            <div className="analysis-stat-cell">
              <div className="analysis-stat-num" style={{ fontSize: "14px", marginTop: "4px" }}>
                {analysis.detected_devices || "N/A"}
              </div>
              <div className="analysis-stat-lbl">Dispositivos</div>
            </div>
          </div>

          <div style={{ marginTop: "16px" }}>
            <h3 style={{ fontSize: "13px", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".04em" }}>
              Datos Extraídos
            </h3>
            <table style={{ marginTop: "8px" }}>
              <tbody>
                <tr>
                  <td style={{ width: "35%", color: "var(--text-dim)", fontWeight: 500 }}>Nombre propuesto</td>
                  <td>{analysis.detected_name || "—"}</td>
                </tr>
                <tr>
                  <td style={{ color: "var(--text-dim)", fontWeight: 500 }}>Versión</td>
                  <td>{analysis.detected_version || "—"}</td>
                </tr>
                <tr>
                  <td style={{ color: "var(--text-dim)", fontWeight: 500 }}>Dispositivo / Plataforma</td>
                  <td>{analysis.detected_platform || "—"}</td>
                </tr>
                <tr>
                  <td style={{ color: "var(--text-dim)", fontWeight: 500 }}>Versión del motor</td>
                  <td>
                    <span className="badge badge-info">{analysis.qc_engine_version}</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          {analysis.observations && analysis.observations.length > 0 && (
            <div style={{ marginTop: "20px" }}>
              <h3 style={{ fontSize: "13px", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".04em" }}>
                Observaciones y Avisos
              </h3>
              <div className="import-issues warning" style={{ marginTop: "8px" }}>
                <div className="import-issues-title">
                  <AlertTriangle size={14} aria-hidden="true" />
                  Hallazgos del análisis determinístico
                </div>
                <ul>
                  {analysis.observations.map((obs, idx) => (
                    <li key={idx}>{obs}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          {analysis.detected_description && (
            <div style={{ marginTop: "16px" }}>
              <h3 style={{ fontSize: "13px", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".04em" }}>
                Descripción extraída
              </h3>
              <div style={{ background: "var(--surface-2)", padding: "12px", borderRadius: "8px", fontSize: "12.5px", marginTop: "8px", lineHeight: "1.5" }}>
                {analysis.detected_description}
              </div>
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button type="button" className="secondary" onClick={onClose}>
            Cerrar
          </button>
        </div>
      </div>
    </div>
  );
}
