"use client";

import { ChevronDown, Download } from "lucide-react";
import { useMemo, useState } from "react";
import { downloadEpicHoursExcel } from "@/lib/exportEpicHours";
import { jiraIssueUrl } from "@/lib/jira";
import { epicProgressEstado, rankEpicProgress, type EpicProgressRow } from "@/lib/qcEffort";

function HoursBar({ value, max }: { value: number; max: number }): React.ReactElement {
  const width = max <= 0 ? 0 : Math.min(100, Math.max(0, (value / max) * 100));
  return (
    <div className="epic-progress-pct hours-only">
      <div className="bar-track">
        {width > 0 ? <div className="bar-fill epic-hours-fill" style={{ width: `${width}%` }} /> : null}
      </div>
    </div>
  );
}

function AdvanceBar({ percent }: { percent: number }): React.ReactElement {
  const width = Math.min(100, Math.max(0, percent));
  return (
    <div className="epic-progress-pct">
      <div className="bar-track">
        {width > 0 ? <div className="bar-fill epic-advance-fill" style={{ width: `${width}%` }} /> : null}
      </div>
      <span className="num">{percent.toFixed(1)}%</span>
    </div>
  );
}

function EpicKey({ rowKey, name }: { rowKey: string; name?: string }): React.ReactElement {
  const href = jiraIssueUrl(rowKey);
  const label = name?.trim() || "";
  const key = href ? (
    <a href={href} target="_blank" rel="noopener noreferrer" title={`Abrir ${rowKey} en Jira`}>
      {rowKey}
    </a>
  ) : (
    rowKey
  );
  return (
    <span className="epic-key">
      {key}
      {label ? <span className="epic-key-name" title={label}>{label}</span> : null}
    </span>
  );
}

export function EpicProgressPanel({
  rows,
  fileName,
}: {
  rows: EpicProgressRow[];
  fileName: string;
}): React.ReactElement {
  const [open, setOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const ranked = useMemo(() => rankEpicProgress(rows), [rows]);
  const maxHours = ranked.reduce((max, row) => Math.max(max, row.hours), 0);
  const totals = ranked.reduce(
    (acc, row) => ({ total: acc.total + row.total, executed: acc.executed + row.executed, hours: acc.hours + row.hours }),
    { total: 0, executed: 0, hours: 0 },
  );
  const totalPercent = totals.total === 0 ? 0 : Math.round((totals.executed * 1000) / totals.total) / 10;
  const totalHours = Math.round(totals.hours * 10) / 10;

  const exportExcel = (): void => {
    setExporting(true);
    void downloadEpicHoursExcel(ranked, fileName).finally(() => setExporting(false));
  };

  return (
    <div className="panel" style={{ margin: "4px 0 14px" }}>
      <button
        type="button"
        className="panel-header epic-hours-toggle"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <h2>Horas / Avance por Technical Epic</h2>
        <ChevronDown size={16} className={open ? "epic-hours-chevron open" : "epic-hours-chevron"} />
      </button>
      {open ? (
        <div className="panel-body">
          <div className="epic-hours-toolbar">
            <p className="muted" style={{ margin: 0 }}>
              De más horas a menos. La barra de horas se llena contra la EPC más grande. La de avance es ejecutados entre casos.
            </p>
            <button type="button" className="secondary" disabled={exporting || ranked.length === 0} onClick={exportExcel}>
              <Download size={14} />
              {exporting ? "Exportando…" : "Exportar"}
            </button>
          </div>
          {ranked.length === 0 ? (
            <p className="muted">Sin casos todavía.</p>
          ) : (
            <table className="activity epic-progress-table">
              <thead>
                <tr>
                  <th>EPC</th>
                  <th className="num">Casos</th>
                  <th className="num">Horas</th>
                  <th aria-label="Barra de horas" />
                  <th className="num">Ejecutados</th>
                  <th>Avance</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                {ranked.map((row) => (
                  <tr key={row.key}>
                    <td><EpicKey rowKey={row.key} name={row.name} /></td>
                    <td className="num">{row.total}</td>
                    <td className="num">{row.hours.toFixed(1)} h</td>
                    <td><HoursBar value={row.hours} max={maxHours} /></td>
                    <td className="num">{row.executed}</td>
                    <td><AdvanceBar percent={row.percent} /></td>
                    <td>{epicProgressEstado(row)}</td>
                  </tr>
                ))}
                <tr className="epic-progress-total">
                  <td><strong>Total</strong></td>
                  <td className="num"><strong>{totals.total}</strong></td>
                  <td className="num"><strong>{totalHours.toFixed(1)} h</strong></td>
                  <td />
                  <td className="num"><strong>{totals.executed}</strong></td>
                  <td><AdvanceBar percent={totalPercent} /></td>
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
