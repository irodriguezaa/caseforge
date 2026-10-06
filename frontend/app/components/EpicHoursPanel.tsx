"use client";

import { Download } from "lucide-react";
import { useMemo, useState } from "react";
import { exportEpicHoursWorkbook } from "@/lib/exportEpicHours";
import { estimateCaseMinutes, type EpicHoursGroup } from "@/lib/qcEffort";

const PREVIEW = 8;

function hoursForCase(row: EpicHoursGroup["cases"][number]): number {
  if (row.estimation_hours != null && Number.isFinite(Number(row.estimation_hours))) {
    return Math.round(Number(row.estimation_hours) * 10) / 10;
  }
  return Math.round((estimateCaseMinutes(row.priority, row.complexity) / 60) * 10) / 10;
}

export function EpicHoursPanel({
  groups,
  fileName,
}: {
  groups: EpicHoursGroup[];
  fileName: string;
}): React.ReactElement {
  const [showAll, setShowAll] = useState(false);
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const visible = useMemo(
    () => (showAll ? groups : groups.slice(0, PREVIEW)),
    [groups, showAll],
  );
  const max = Math.max(1, ...groups.map((row) => row.hours));

  async function handleExport(): Promise<void> {
    setExporting(true);
    setExportError(null);
    try {
      await exportEpicHoursWorkbook(groups, fileName);
    } catch (err: unknown) {
      setExportError(err instanceof Error ? err.message : "No se pudo exportar.");
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="panel" style={{ margin: "4px 0 14px" }}>
      <div className="panel-header">
        <h2>Horas por Technical Epic</h2>
        <button
          type="button"
          className="secondary"
          disabled={exporting || groups.length === 0}
          onClick={() => void handleExport()}
        >
          <Download size={14} aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: "6px" }} />
          {exporting ? "Exportando..." : "Exportar"}
        </button>
      </div>
      <div className="panel-body">
        <p className="muted" style={{ marginTop: 0, marginBottom: "10px" }}>
          Click en un EPC para ver sus casos. Se agrupa por Componente (un key de Jira). Si el origen
          traía varios tickets unidos con |, se usa el primero.
        </p>
        {exportError ? <p className="error-text">{exportError}</p> : null}
        {visible.length === 0 ? (
          <p className="muted">Sin datos todavía.</p>
        ) : (
          <div className="epic-hours-list">
            {visible.map((group) => {
              const open = openKey === group.key;
              return (
                <div key={group.key} className={`epic-hours-item${open ? " open" : ""}`}>
                  <button
                    type="button"
                    className="epic-hours-row"
                    onClick={() => setOpenKey(open ? null : group.key)}
                    aria-expanded={open}
                  >
                    <span className="epic-hours-key" title={group.key}>
                      {group.key}
                    </span>
                    <span className="epic-hours-track">
                      <span
                        className="epic-hours-fill"
                        style={{ width: `${(group.hours / max) * 100}%` }}
                      />
                    </span>
                    <span className="epic-hours-meta">
                      {group.hours.toFixed(1)} h · {group.cases.length}
                    </span>
                  </button>
                  {open && (
                    <table className="activity" style={{ marginTop: "8px" }}>
                      <thead>
                        <tr>
                          <th>ID</th>
                          <th>Nombre</th>
                          <th>Prioridad</th>
                          <th className="num">Horas</th>
                        </tr>
                      </thead>
                      <tbody>
                        {group.cases.map((row) => (
                          <tr key={row.test_case_id}>
                            <td>{row.test_case_id}</td>
                            <td>{row.test_case_name}</td>
                            <td>{row.priority || "—"}</td>
                            <td className="num">{hoursForCase(row).toFixed(1)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              );
            })}
          </div>
        )}
        {groups.length > PREVIEW && (
          <button
            type="button"
            className="secondary"
            style={{ marginTop: "10px" }}
            onClick={() => setShowAll((value) => !value)}
          >
            {showAll ? "Ver menos" : `Ver todas (${groups.length})`}
          </button>
        )}
      </div>
    </div>
  );
}
