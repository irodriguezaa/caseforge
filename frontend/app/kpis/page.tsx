"use client";

import { useCallback, useEffect, useState } from "react";
import { BarList } from "@/app/components/BarList";
import { QcTicketUploadCard } from "@/app/components/QcTicketUploadCard";
import { api } from "@/lib/api";
import type { QcRadarConfigResponse, QcTicketStats, QcTicketView } from "@/lib/types";

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

function ViewPanel({
  view,
  config,
}: {
  view: QcTicketView;
  config: QcRadarConfigResponse | null;
}): React.ReactElement {
  const [stats, setStats] = useState<QcTicketStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback((): void => {
    api.getQcTicketStats(view).then(setStats).catch((err: unknown) => setError(err instanceof Error ? err.message : "Error"));
  }, [view]);

  useEffect(load, [load]);

  const viewConfig = config ? config[view] : null;
  const detectLabel = viewConfig ? viewConfig.detected.label : (view === "OPERATIVAS" ? "Detección QC" : "QC + QA Bugs");
  const detectTag = viewConfig ? viewConfig.detected.tag : (view === "OPERATIVAS" ? "#112929" : "#113261");
  const leakLabel = viewConfig ? viewConfig.leaked.label : "Fuga de defectos";
  const leakTag = viewConfig ? viewConfig.leaked.tag : (view === "OPERATIVAS" ? "#113062" : "#113784");

  return (
    <>
      {error && <p className="error-text">{error}</p>}

      {stats && (
        <>
          {/* KPI strip: totals with a color-coded breakdown, mirrors the reference tool's header row */}
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
              <div className="kpi-sub">vía {detectTag}</div>
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
                  ? `de ${stats.leaked_count} brutos vía ${leakTag}`
                  : `${stats.leaked_count} vía ${leakTag}`}
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
        <QcTicketUploadCard title={detectLabel} filterTag={detectTag} view={view} source="QC_DETECTED" onImported={load} />
        <QcTicketUploadCard title={leakLabel} filterTag={leakTag} view={view} source="LEAKED" onImported={load} />
      </div>
    </>
  );
}

export default function KpisPage(): React.ReactElement {
  const [tab, setTab] = useState<QcTicketView>("OPERATIVAS");
  const [config, setConfig] = useState<QcRadarConfigResponse | null>(null);

  useEffect(() => {
    api.getQcRadarConfig().then(setConfig).catch(() => setConfig(null));
  }, []);

  return (
    <div className="page page-wide">
      <p className="eyebrow">KPIs</p>
      <h1>Radar de Defectos</h1>
      <p className="subtitle">Volumetría de tickets QC — independiente de Releases y Test Cases</p>

      <div className="tabnav">
        <button type="button" className={tab === "OPERATIVAS" ? "active" : ""} onClick={() => setTab("OPERATIVAS")}>
          Operativas
        </button>
        <button type="button" className={tab === "RELEASE" ? "active" : ""} onClick={() => setTab("RELEASE")}>
          Release
        </button>
      </div>

      <ViewPanel view={tab} config={config} key={tab} />
    </div>
  );
}
