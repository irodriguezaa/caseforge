"use client";

import { Download, X } from "lucide-react";
import { useState } from "react";
import { downloadCandidatesExcel } from "@/lib/exportGeneratedCandidates";
import { stripDeviceFromCaseName } from "@/lib/qcEffort";
import type { GenerateCasesResponse } from "@/lib/types";

export function GeneratedCasesPreview({
  result,
  onClose,
}: {
  result: GenerateCasesResponse;
  onClose: () => void;
}): React.ReactElement {
  const [exporting, setExporting] = useState(false);
  const canExport = result.candidates.length > 0;

  const handleExport = (): void => {
    if (!canExport || exporting) {
      return;
    }
    setExporting(true);
    window.setTimeout(() => {
      void downloadCandidatesExcel(result.candidates, result.release_name).finally(() => {
        setExporting(false);
      });
    }, 0);
  };

  return (
    <div className="card generated-preview">
      <div className="section-header" style={{ marginTop: 0 }}>
        <h2>Candidatos de Test Cases</h2>
        <div className="form-actions" style={{ margin: 0 }}>
          <button
            type="button"
            onClick={handleExport}
            disabled={!canExport || exporting}
          >
            <Download size={14} aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: "6px" }} />
            {exporting ? "Exportando…" : "Exportar a Excel"}
          </button>
          <button type="button" className="icon-close" onClick={onClose} aria-label="Cerrar preview">
            <X size={16} />
          </button>
        </div>
      </div>
      <p className="muted" style={{ marginTop: "-6px", fontSize: "12.5px" }}>
        {result.message} Motor: {result.engine}. La IA propone; QC decide. Aún no se guardan en
        la base de datos.
      </p>
      {result.candidates.length === 0 ? (
        <p className="muted">No hay candidatos para revisar.</p>
      ) : (
        <ul className="candidate-list">
          {result.candidates.map((candidate, index) => (
            <li key={`${candidate.related_jira ?? candidate.name}-${index}`} className="candidate-card">
              <div className="candidate-card-head">
                <strong>{stripDeviceFromCaseName(candidate.name, candidate.device)}</strong>
                <span className={`badge badge-${candidate.confidence === "high" ? "ok" : candidate.confidence === "low" ? "warning" : "info"}`}>
                  {candidate.confidence}
                </span>
                {candidate.requires_condition && (
                  <span className="badge badge-warning">requiere condición</span>
                )}
                {candidate.possible_duplicate_of && (
                  <span className="badge badge-warning">
                    {candidate.duplicate_status === "OVERLAP" ? "solapamiento" : "posible duplicado"}
                  </span>
                )}
                {candidate.review_required && (
                  <span className="badge badge-neutral">revisión QC</span>
                )}
                {candidate.basic_validation && (
                  <span className="badge badge-neutral">validación básica</span>
                )}
              </div>
              <p>{candidate.description}</p>
              {candidate.precondition && (
                <p>
                  <span className="muted">Precondición: </span>
                  {candidate.precondition}
                </p>
              )}
              <ol className="candidate-steps">
                {candidate.steps.map((step) => (
                  <li key={step.step_number}>
                    <div>{step.action}</div>
                    <div className="muted">Esperado: {step.expected_result}</div>
                    {step.test_data && (
                      <div className="muted">Datos de prueba: {step.test_data}</div>
                    )}
                  </li>
                ))}
              </ol>
              <dl className="candidate-meta">
                {candidate.related_functionality && (
                  <>
                    <dt>Funcionalidad</dt>
                    <dd>{candidate.related_functionality}</dd>
                  </>
                )}
                {candidate.related_jira && (
                  <>
                    <dt>Jira</dt>
                    <dd>{candidate.related_jira}</dd>
                  </>
                )}
                {candidate.hn_keys && candidate.hn_keys.length > 0 && (
                  <>
                    <dt>HN/CA</dt>
                    <dd>{candidate.hn_keys.join(", ")}</dd>
                  </>
                )}
                {candidate.hn_source && (
                  <>
                    <dt>Origen HN</dt>
                    <dd>{candidate.hn_source}</dd>
                  </>
                )}
                {candidate.use_case_title && (
                  <>
                    <dt>Caso de uso</dt>
                    <dd>{candidate.use_case_title}</dd>
                  </>
                )}
                {candidate.user_type && (
                  <>
                    <dt>Usuario</dt>
                    <dd>{candidate.user_type}</dd>
                  </>
                )}
                {candidate.group_id && (
                  <>
                    <dt>Group ID</dt>
                    <dd>{candidate.group_id}</dd>
                  </>
                )}
                {candidate.interaction_points && candidate.interaction_points.length > 0 && (
                  <>
                    <dt>Canal / Punto de interacción</dt>
                    <dd>{candidate.interaction_points.join(", ")}</dd>
                  </>
                )}
                {candidate.related_rn && (
                  <>
                    <dt>RN</dt>
                    <dd>{candidate.related_rn}</dd>
                  </>
                )}
                <dt>Evidencia</dt>
                <dd>{candidate.evidence}</dd>
                {candidate.test_data && (
                  <>
                    <dt>Datos de prueba</dt>
                    <dd>{candidate.test_data}</dd>
                  </>
                )}
                <dt>Justificación</dt>
                <dd>{candidate.justification}</dd>
                {candidate.possible_duplicate_of && (
                  <>
                    <dt>{candidate.duplicate_status === "OVERLAP" ? "Solapa con" : "Posible duplicado de"}</dt>
                    <dd>
                      {candidate.duplicate_with?.length
                        ? candidate.duplicate_with.join(", ")
                        : candidate.possible_duplicate_of}
                    </dd>
                  </>
                )}
                {candidate.device_source && (
                  <>
                    <dt>Fuente dispositivo</dt>
                    <dd>{candidate.device_source}</dd>
                  </>
                )}
                {candidate.ecosystem && (
                  <>
                    <dt>Ecosistema</dt>
                    <dd>{candidate.ecosystem}</dd>
                  </>
                )}
                {candidate.applicability_reason && (
                  <>
                    <dt>Aplicabilidad</dt>
                    <dd>{candidate.applicability_reason}</dd>
                  </>
                )}
                {candidate.priority_reason && (
                  <>
                    <dt>Prioridad</dt>
                    <dd>
                      {candidate.priority ?? "Pendiente"} — {candidate.priority_reason}
                    </dd>
                  </>
                )}
              </dl>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
