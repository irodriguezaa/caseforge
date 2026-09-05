"use client";

import type { ReleaseAnalysis } from "@/lib/types";

interface ReleaseAnalysisCardProps {
  analysis: ReleaseAnalysis;
  qcResources?: number | null;
  executionDays?: number | null;
}

export function ReleaseAnalysisCard({
  analysis,
  qcResources,
  executionDays,
}: ReleaseAnalysisCardProps): React.ReactElement {
  return (
    <div className="card" style={{ borderLeft: "3px solid var(--accent)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
          <h2>Análisis de Release</h2>
          <span className="badge badge-info" style={{ fontSize: "11px" }}>
            QC Engine: {analysis.qc_engine_version}
          </span>
        </div>

        {/* Únicamente las 4 métricas pedidas -- sin Dispositivos, Cobertura propuesta ni
            Estimación. Estilos en línea: label y valor van agrupados en la misma celda, en
            grid horizontal cuando hay espacio -- no depende de clases CSS externas no verificadas. */}
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
                borderRadius: "8px",
                padding: "10px 14px",
              }}
            >
              <div style={{ fontSize: "10.5px", textTransform: "uppercase", letterSpacing: ".04em", color: "var(--text-dim)" }}>
                {stat.label}
              </div>
              <div style={{ fontSize: "22px", fontWeight: 700, marginTop: "2px" }}>{stat.value}</div>
            </div>
          ))}
        </div>

        {executionDays !== undefined && executionDays !== null && executionDays > 0 && qcResources ? (
          <p className="muted" style={{ fontSize: "12.5px", margin: "14px 0 0" }}>
            Estimación de IA: con los recursos asignados, la ejecución estimada es de {executionDays} día{executionDays > 1 ? "s" : ""}.
          </p>
        ) : null}
      </div>
  );
}
