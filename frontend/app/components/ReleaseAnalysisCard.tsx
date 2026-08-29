"use client";

import { AlertTriangle, Eye, Sparkles } from "lucide-react";
import { useState } from "react";
import { ReleaseAnalysisModal } from "@/app/components/ReleaseAnalysisModal";
import type { ReleaseAnalysis } from "@/lib/types";

interface ReleaseAnalysisCardProps {
  analysis: ReleaseAnalysis;
  qcResources?: number | null;
  executionDays?: number | null;
  onGenerateClick?: () => void;
}

export function ReleaseAnalysisCard({
  analysis,
  qcResources,
  executionDays,
  onGenerateClick,
}: ReleaseAnalysisCardProps): React.ReactElement {
  const [modalOpen, setModalOpen] = useState(false);

  // Estimation string calculated from QC config if available
  const estimationDisplay =
    qcResources && executionDays
      ? `${qcResources} recurso${qcResources > 1 ? "s" : ""} / ${executionDays} día${executionDays > 1 ? "s" : ""}`
      : "Configurar en paso 3";

  // Coverage display placeholder for Phase 1 (QC engine will calculate in future)
  const coverageDisplay = analysis.proposed_coverage
    ? `${analysis.proposed_coverage} casos`
    : "Se definirá por motor QC";

  return (
    <>
      <div className="card" style={{ borderLeft: "3px solid var(--accent)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
          <h2>Análisis de Release</h2>
          <span className="badge badge-info" style={{ fontSize: "11px" }}>
            QC Engine: {analysis.qc_engine_version}
          </span>
        </div>

        <div className="analysis-stat-grid">
          <div className="analysis-stat-cell">
            <div className="analysis-stat-num">{analysis.features_count}</div>
            <div className="analysis-stat-lbl">Funcionalidades detectadas</div>
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
            <div className="analysis-stat-num" style={{ fontSize: "14px", marginTop: "3px" }}>
              {analysis.detected_devices || analysis.detected_platform || "WIN / XBOX"}
            </div>
            <div className="analysis-stat-lbl">Dispositivos</div>
          </div>
          <div className="analysis-stat-cell">
            <div className="analysis-stat-num" style={{ fontSize: "14px", marginTop: "3px", color: "var(--text)" }}>
              {coverageDisplay}
            </div>
            <div className="analysis-stat-lbl">Cobertura propuesta</div>
          </div>
          <div className="analysis-stat-cell">
            <div className="analysis-stat-num" style={{ fontSize: "14px", marginTop: "3px", color: "var(--text)" }}>
              {estimationDisplay}
            </div>
            <div className="analysis-stat-lbl">Estimación</div>
          </div>
        </div>

        {analysis.observations && analysis.observations.length > 0 && (
          <div style={{ margin: "14px 0 10px", fontSize: "12.5px", color: "var(--warning)" }}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: "6px", fontWeight: 600 }}>
              <AlertTriangle size={14} aria-hidden="true" />
              {analysis.observations.length} observación{analysis.observations.length > 1 ? "es" : ""} detectada{analysis.observations.length > 1 ? "s" : ""} en el documento
            </span>
          </div>
        )}

        <div className="form-actions" style={{ marginTop: "14px" }}>
          <button type="button" className="secondary" onClick={() => setModalOpen(true)}>
            <Eye size={14} style={{ verticalAlign: "-2px", marginRight: "6px" }} />
            Ver análisis
          </button>
          <button
            type="button"
            onClick={onGenerateClick}
            style={{ background: "var(--accent-dim)", color: "#a9c8fb", border: "1px solid var(--accent)" }}
          >
            <Sparkles size={14} style={{ verticalAlign: "-2px", marginRight: "6px" }} />
            Generar casos
          </button>
        </div>
      </div>

      {modalOpen && (
        <ReleaseAnalysisModal analysis={analysis} onClose={() => setModalOpen(false)} />
      )}
    </>
  );
}
