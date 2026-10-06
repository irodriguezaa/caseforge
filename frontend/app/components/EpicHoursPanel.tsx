"use client";

import { ChevronDown, Download } from "lucide-react";
import { useState } from "react";
import { BarList } from "@/app/components/BarList";
import { downloadEpicHoursExcel } from "@/lib/exportEpicHours";

export function EpicHoursPanel({
  items,
  fileName,
}: {
  items: { label: string; value: number }[];
  fileName: string;
}): React.ReactElement {
  const [open, setOpen] = useState(false);
  const [exporting, setExporting] = useState(false);

  const exportExcel = (): void => {
    setExporting(true);
    void downloadEpicHoursExcel(items, fileName).finally(() => setExporting(false));
  };

  return (
    <div className="panel" style={{ margin: "4px 0 14px" }}>
      <button
        type="button"
        className="panel-header epic-hours-toggle"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <h2>Horas por Technical Epic</h2>
        <ChevronDown size={16} className={open ? "epic-hours-chevron open" : "epic-hours-chevron"} />
      </button>
      {open ? (
        <div className="panel-body">
          <div className="epic-hours-toolbar">
            <p className="muted" style={{ margin: 0 }}>
              Esfuerzo estimado QC consolidado por EPC. La etiqueta es el key de Jira.
            </p>
            <button type="button" className="secondary" disabled={exporting || items.length === 0} onClick={exportExcel}>
              <Download size={14} />
              {exporting ? "Exportando…" : "Exportar"}
            </button>
          </div>
          <BarList
            items={items}
            color="var(--kpi-teal, var(--accent))"
            wideLabels
            formatValue={(value) => `${value.toFixed(1)} h`}
          />
        </div>
      ) : null}
    </div>
  );
}
