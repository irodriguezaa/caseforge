"use client";

import { ChevronDown } from "lucide-react";
import { useState } from "react";
import { jiraIssueUrl } from "@/lib/jira";
import type { EpicProgressRow } from "@/lib/qcEffort";

export function EpicProgressPanel({ rows }: { rows: EpicProgressRow[] }): React.ReactElement {
  const [open, setOpen] = useState(true);
  const totals = rows.reduce(
    (acc, row) => ({ total: acc.total + row.total, executed: acc.executed + row.executed, hours: acc.hours + row.hours }),
    { total: 0, executed: 0, hours: 0 },
  );
  const totalPercent = totals.total === 0 ? 0 : Math.round((totals.executed * 1000) / totals.total) / 10;

  return (
    <div className="panel" style={{ margin: "4px 0 14px" }}>
      <button
        type="button"
        className="panel-header epic-hours-toggle"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <h2>Avance por Technical Epic</h2>
        <ChevronDown size={16} className={open ? "epic-hours-chevron open" : "epic-hours-chevron"} />
      </button>
      {open ? (
        <div className="panel-body">
          <p className="muted" style={{ marginTop: 0, marginBottom: "10px" }}>
            Ejecutado = todo lo que no es UNEXECUTED. Las horas son la estimación QC, no el avance.
          </p>
          {rows.length === 0 ? (
            <p className="muted">Sin casos todavía.</p>
          ) : (
            <table className="activity epic-progress-table">
              <thead>
                <tr>
                  <th>EPC</th>
                  <th className="num">Casos</th>
                  <th className="num">Ejecutados</th>
                  <th className="num">%</th>
                  <th className="num">Horas</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const href = jiraIssueUrl(row.key);
                  return (
                    <tr key={row.key}>
                      <td>
                        {href ? (
                          <a href={href} target="_blank" rel="noopener noreferrer" title={`Abrir ${row.key} en Jira`}>
                            {row.key}
                          </a>
                        ) : (
                          row.key
                        )}
                      </td>
                      <td className="num">{row.total}</td>
                      <td className="num">{row.executed}</td>
                      <td>
                        <div className="epic-progress-pct">
                          <div className="bar-track">
                            <div
                              className="bar-fill epic-progress-fill"
                              style={{ width: `${Math.min(100, Math.max(0, row.percent))}%` }}
                            />
                          </div>
                          <span className="num">{row.percent.toFixed(1)}%</span>
                        </div>
                      </td>
                      <td className="num">{row.hours.toFixed(1)}</td>
                      <td>{row.orphan ? "huérfano" : row.estado || "—"}</td>
                    </tr>
                  );
                })}
                <tr>
                  <td><strong>Total</strong></td>
                  <td className="num"><strong>{totals.total}</strong></td>
                  <td className="num"><strong>{totals.executed}</strong></td>
                  <td>
                    <div className="epic-progress-pct">
                      <div className="bar-track">
                        <div
                          className="bar-fill epic-progress-fill"
                          style={{ width: `${Math.min(100, Math.max(0, totalPercent))}%` }}
                        />
                      </div>
                      <span className="num"><strong>{totalPercent.toFixed(1)}%</strong></span>
                    </div>
                  </td>
                  <td className="num"><strong>{Math.round(totals.hours * 10) / 10}</strong></td>
                  <td />
                </tr>
              </tbody>
            </table>
          )}
        </div>
      ) : null}
    </div>
  );
}
