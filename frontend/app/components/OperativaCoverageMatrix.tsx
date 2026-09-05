"use client";

import type { CoverageMatrixResponse } from "@/lib/types";

interface OperativaCoverageMatrixProps {
  data: CoverageMatrixResponse;
  brfFilter?: string;
}

export function OperativaCoverageMatrix({ data, brfFilter }: OperativaCoverageMatrixProps): React.ReactElement {
  const rows = brfFilter
    ? data.rows.filter((row) => row.brf_key.toUpperCase() === brfFilter.toUpperCase())
    : data.rows;

  return (
    <div className="card" style={{ marginTop: "1rem" }}>
      <h2>Clasificación de HN y comportamientos</h2>
      <p className="muted" style={{ marginBottom: "0.75rem" }}>
        {data.engine} · {data.row_count} comportamiento(s) · {data.brfs_analyzed} BRF(s)
        {brfFilter ? ` · filtro ${brfFilter}` : ""}
      </p>
      {data.notes.length > 0 && (
        <ul className="muted" style={{ fontSize: "12px", marginBottom: "1rem" }}>
          {data.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
      {data.hn_coverage && data.hn_coverage.length > 0 && (
        <div style={{ overflowX: "auto", marginBottom: "1rem" }}>
          <h3 style={{ fontSize: "14px", margin: "0 0 0.5rem" }}>Clasificación de HN</h3>
          <p className="muted" style={{ fontSize: "12px", marginBottom: "0.5rem" }}>
            Toda HN tiene disposición. SUPPORTING y TEST_DATA se incorporan; OOS_QC no genera TC de QC.
          </p>
          <table className="data-table">
            <thead>
              <tr>
                <th>HN</th>
                <th>Disposición</th>
                <th>Relacionada</th>
                <th>Comportamiento</th>
                <th>Razón</th>
              </tr>
            </thead>
            <tbody>
              {data.hn_coverage
                .filter((item) => !brfFilter || item.brf_key.toUpperCase() === brfFilter.toUpperCase())
                .map((item) => (
                  <tr key={`${item.brf_key}-${item.hn_key}`}>
                    <td>
                      {item.brf_key} {item.hn_key}
                    </td>
                    <td>{item.disposition || item.status}</td>
                    <td>{item.related_hn?.join(", ") || "—"}</td>
                    <td>{item.behavior_keys.join(", ") || "—"}</td>
                    <td title={item.reason}>{item.reason}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}
      <div style={{ overflowX: "auto" }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>BRF</th>
              <th>HN</th>
              <th>Comportamiento</th>
              <th>Canal / Punto de interacción</th>
              <th>Ecosistema</th>
              <th>Dispositivos</th>
              <th>Usuarios</th>
              <th>MDP</th>
              <th>EPCs</th>
              <th>Dup.</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.behavior_key}>
                <td>{row.brf_key}</td>
                <td>{row.hn_keys.join(", ") || "—"}</td>
                <td title={row.behavior_key}>{row.behavior_title}</td>
                <td>
                  {[...row.interaction_points, row.channel].filter(Boolean).join(", ") || "—"}
                </td>
                <td>{row.ecosystem ?? (row.channel ? "—" : "—")}</td>
                <td>{row.applicable_devices.length ? row.applicable_devices.join(", ") : row.channel ? "—" : "—"}</td>
                <td>{row.relevant_users.length ? row.relevant_users.join(", ") : "—"}</td>
                <td>{row.mdp.length ? row.mdp.join(", ") : "—"}</td>
                <td>{row.epc_keys.join(", ")}</td>
                <td>{row.duplicate_risk === "UNIQUE" ? "—" : row.duplicate_risk}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
