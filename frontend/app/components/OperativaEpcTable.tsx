"use client";

import type { EpcRead } from "@/lib/types";

const SUGGESTION_LABEL: Record<EpcRead["qc_suggestion"], string> = {
  SUGERIDO_INCLUIR: "Sugerido: incluir",
  SUGERIDO_EXCLUIR: "Sugerido: excluir",
  REQUIERE_REVISION: "Requiere revisión",
};

const SUGGESTION_COLOR: Record<EpcRead["qc_suggestion"], string> = {
  SUGERIDO_INCLUIR: "var(--success)",
  SUGERIDO_EXCLUIR: "var(--danger)",
  REQUIERE_REVISION: "var(--warning)",
};

export function OperativaEpcTable({
  epcs,
  onToggleInclude,
  readOnly = false,
}: {
  epcs: EpcRead[];
  onToggleInclude?: (epc: EpcRead, includeInQc: boolean) => void;
  readOnly?: boolean;
}): React.ReactElement {
  return (
    <table className="activity">
      <thead>
        <tr>
          <th>BRF</th>
          <th>EPC</th>
          <th>Título</th>
          <th>Estado Jira</th>
          <th>Alcance</th>
          <th>Nota RTE</th>
          <th>Sugerencia del sistema</th>
          {!readOnly && <th>Incluir en QC</th>}
        </tr>
      </thead>
      <tbody>
        {epcs.map((epc) => (
          <tr key={epc.id}>
            <td style={{ fontWeight: 500 }}>{epc.brf_key}</td>
            <td className="muted">{epc.epc_key ?? "—"}</td>
            <td className="muted" style={{ maxWidth: "260px" }}>{epc.titulo}</td>
            <td className="muted">{epc.estado_jira ?? "—"}</td>
            <td className="muted">{epc.alcance ?? "—"}</td>
            <td className="muted" style={{ maxWidth: "200px", fontSize: "11.5px" }}>{epc.nota_rte ?? "—"}</td>
            <td>
              <span style={{ color: SUGGESTION_COLOR[epc.qc_suggestion], fontWeight: 600, fontSize: "11.5px" }}>
                {SUGGESTION_LABEL[epc.qc_suggestion]}
              </span>
            </td>
            {!readOnly && (
            <td>
              <label style={{ display: "inline-flex", alignItems: "center", gap: "6px", cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={epc.include_in_qc}
                  onChange={(e) => onToggleInclude?.(epc, e.target.checked)}
                />
              </label>
            </td>
            )}
          </tr>
        ))}
        {epcs.length === 0 && (
          <tr>
            <td colSpan={readOnly ? 7 : 8} className="muted">
              {readOnly ? "No hay EPCs incluidos en este Release." : "No se detectaron EPCs en este RN."}
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}
