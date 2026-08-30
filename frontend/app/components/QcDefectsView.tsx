"use client";

import { useCallback, useEffect, useState } from "react";
import { BarList } from "@/app/components/BarList";
import { QcTicketUploadCard } from "@/app/components/QcTicketUploadCard";
import { api } from "@/lib/api";
import type { QcTicketStats, QcTicketView } from "@/lib/types";

function sortedEntries(record: Record<string, number>): { label: string; value: number }[] {
  return Object.entries(record)
    .map(([label, value]) => ({ label, value }))
    .sort((a, b) => b.value - a.value);
}

function MonthBars({ byMonth }: { byMonth: Record<string, number> }): React.ReactElement {
  const entries = Object.entries(byMonth).sort(([a], [b]) => a.localeCompare(b));
  const max = Math.max(1, ...entries.map(([, v]) => v));
  return (
    <div className="month-bars">
      {entries.map(([month, value]) => (
        <div className="month-bar-col" key={month}>
          <span className="month-bar-value">{value}</span>
          <div className="month-bar" style={{ height: `${(value / max) * 100}%` }} />
          <span className="month-bar-label">{month.slice(5)}</span>
        </div>
      ))}
      {entries.length === 0 && <p className="muted">Sin datos todavía.</p>}
    </div>
  );
}

const FILTER_TAGS: Record<QcTicketView, { detected: string; leaked: string }> = {
  OPERATIVAS: { detected: "#112929", leaked: "#113062" },
  RELEASE: { detected: "#113261", leaked: "#113784" },
};

const PAGE_COPY: Record<QcTicketView, { eyebrow: string; title: string; subtitle: string }> = {
  OPERATIVAS: {
    eyebrow: "KPIs · Defectos Operativa",
    title: "Radar de Defectos — Operativa",
    subtitle: "Volumetría de tickets QC Operativos — independiente de Releases y Test Cases",
  },
  RELEASE: {
    eyebrow: "KPIs · Defectos Release",
    title: "Radar de Defectos — Release",
    subtitle: "Volumetría de tickets QC de Release — independiente de Releases y Test Cases",
  },
};

/**
 * Single defects dashboard, parameterized by view. Used by /kpis/operativas and /kpis/release
 * as two separate routes (no more in-page Operativas/Release tab toggle) -- each mounts its own
 * instance, so switching between them via the sidebar never carries state/data from the other.
 */
export function QcDefectsView({ view }: { view: QcTicketView }): React.ReactElement {
  const [stats, setStats] = useState<QcTicketStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback((): void => {
    api.getQcTicketStats(view).then(setStats).catch((err: unknown) => setError(err instanceof Error ? err.message : "Error"));
  }, [view]);

  useEffect(load, [load]);

  const detectLabel = view === "OPERATIVAS" ? "Detección QC" : "QC + QA Bugs";
  const leakLabel = "Fuga de defectos";
  const tags = FILTER_TAGS[view];
  const copy = PAGE_COPY[view];

  return (
    <div className="page page-wide">
      <p className="eyebrow">{copy.eyebrow}</p>
      <h1>{copy.title}</h1>
      <p className="subtitle">{copy.subtitle}</p>

      {error && <p className="error-text">{error}</p>}

      {stats && (
        <>
          <div className="kpi-strip">
            <div className="kpi-cell">
              <div className="kpi-num">{stats.total}</div>
              <div className="kpi-lbl">Total</div>
              <div className="kpi-sub">
                <span className="chip-dot"><span className="dot blocker" />{stats.blocker_count} Blocker</span>
                <span className="chip-dot"><span className="dot critica" />{stats.critical_count} Crítica</span>
                <span className="chip-dot"><span className="dot otros" />{stats.other_count} Otros</span>
              </div>
            </div>
            <div className="kpi-cell">
              <div className="kpi-num">{stats.open_count}</div>
              <div className="kpi-lbl">Backlog abierto</div>
              <div className="kpi-sub">{stats.total ? Math.round((stats.open_count / stats.total) * 100) : 0}% del total</div>
            </div>
            <div className="kpi-cell">
              <div className="kpi-num">{stats.qc_detected_count}</div>
              <div className="kpi-lbl">Detectados</div>
              <div className="kpi-sub">vía {tags.detected}</div>
            </div>
            <div className="kpi-cell">
              <div className="kpi-num accent">
                {view === "RELEASE" && stats.genuine_leak_count !== null
                  ? stats.genuine_leak_count
                  : `${stats.leak_rate_percent}%`}
              </div>
              <div className="kpi-lbl">{view === "RELEASE" ? "Fuga genuina" : "Tasa de fuga"}</div>
              <div className="kpi-sub">
                {view === "RELEASE" && stats.genuine_leak_count !== null
                  ? `de ${stats.leaked_count} brutos vía ${tags.leaked}`
                  : `${stats.leaked_count} vía ${tags.leaked}`}
              </div>
            </div>
          </div>

          <div className="section-label first">Distribución</div>
          <div className={view === "OPERATIVAS" ? "grid-two" : ""}>
            <div className="panel">
              <div className="panel-header"><h2>Por SWF</h2></div>
              <div className="panel-body">
                <BarList items={sortedEntries(stats.by_swf)} color="var(--accent)" />
              </div>
            </div>
            {view === "OPERATIVAS" && (
              <div className="panel">
                <div className="panel-header"><h2>Por Cluster</h2></div>
                <div className="panel-body">
                  <BarList items={sortedEntries(stats.by_cluster)} color="var(--success)" />
                </div>
              </div>
            )}
          </div>

          <div className="section-label">Tendencia mensual</div>
          <div className="panel">
            <div className="panel-header"><h2>Detección por mes</h2></div>
            <div className="panel-body">
              <MonthBars byMonth={stats.by_month} />
            </div>
          </div>
        </>
      )}

      <div className="section-label">Cargar tickets</div>
      <div className="form-grid">
        <QcTicketUploadCard title={detectLabel} filterTag={tags.detected} view={view} source="QC_DETECTED" onImported={load} />
        <QcTicketUploadCard title={leakLabel} filterTag={tags.leaked} view={view} source="LEAKED" onImported={load} />
      </div>
    </div>
  );
}
