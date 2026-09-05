"use client";

import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { BarList } from "@/app/components/BarList";
import { DonutChart } from "@/app/components/DonutChart";
import { InfoTooltip } from "@/app/components/InfoTooltip";
import { LeakTrendChart } from "@/app/components/LeakTrendChart";
import { StackedBarChart } from "@/app/components/StackedBarChart";
import { api, ApiRequestError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { QcTicketStats, QcTicketView } from "@/lib/types";

type BugTypeFilter = "ALL" | "QC" | "QA";

function sortedEntries(record: Record<string, number>): { label: string; value: number }[] {
  return Object.entries(record)
    .map(([label, value]) => ({ label, value }))
    .sort((a, b) => b.value - a.value);
}

const PRIORITY_COLORS: Record<string, string> = {
  BLOCKER: "var(--kpi-blue)",
  CRITICAL: "var(--kpi-teal)",
  OTHER: "var(--kpi-gray)",
};
const PRIORITY_CATEGORIES = ["BLOCKER", "CRITICAL", "OTHER"];

const FILTER_TAGS: Record<QcTicketView, { detected: string; leaked: string }> = {
  OPERATIVAS: { detected: "#112929", leaked: "#113062" },
  RELEASE: { detected: "#113261", leaked: "#113784" },
};

function formatUpdatedAt(date: Date): string {
  return date.toLocaleString("es-MX", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const PAGE_COPY: Record<QcTicketView, { eyebrow: string; title: string; subtitle: string }> = {
  OPERATIVAS: {
    eyebrow: "KPIs · Defectos Operativa",
    title: "Radar de Defectos — Operativa",
    subtitle: "Volumetría de tickets QC de Ventanas Operativas",
  },
  RELEASE: {
    eyebrow: "KPIs · Defectos Release",
    title: "Radar de Defectos — Release",
    subtitle: "Volumetría de tickets QC Release",
  },
};

/**
 * Single defects dashboard, parameterized by view. Used by /kpis/operativas and /kpis/release
 * as two separate routes -- each mounts its own instance, so switching between them via the
 * sidebar never carries state/data from the other.
 *
 * Section order (both views) follows the agreed canonical sequence: Volumetría -> Tendencia
 * mensual -> Distribución -> Backlog -> [Release only: Severidad por SWF -> Composición de SWF
 * por mes] -> Top dispositivos -> Fuga de defectos (only shown at all in Operativa, or in
 * Release's QA+QC view -- always last).
 */
export function QcDefectsView({ view }: { view: QcTicketView }): React.ReactElement {
  const { canRefreshKpis } = useAuth();
  const [stats, setStats] = useState<QcTicketStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [bugType, setBugType] = useState<BugTypeFilter>("ALL");
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [refreshSummary, setRefreshSummary] = useState<string | null>(null);

  const load = useCallback((): void => {
    const apiBugType = view === "RELEASE" && bugType !== "ALL" ? bugType : undefined;
    api
      .getQcTicketStats(view, undefined, apiBugType)
      .then((data) => {
        setStats(data);
        setError(null);
        setLastUpdated(new Date());
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Error"));
  }, [view, bugType]);

  useEffect(load, [load]);

  const refreshFromJira = useCallback(async (): Promise<void> => {
    setRefreshing(true);
    setError(null);
    try {
      await api.refreshQcTicketsFromJira(view).then((result) => {
        const byFilter = (result.filters ?? [])
          .map((item) => `#${item.filter_id}: ${item.jira_count} en Jira → ${item.mapped} cargados`)
          .join(" · ");
        setRefreshSummary(byFilter || `Creados ${result.created} · actualizados ${result.updated}`);
      });
      load();
    } catch (err: unknown) {
      const message =
        err instanceof ApiRequestError
          ? err.message
          : err instanceof Error
            ? err.message
            : "No se pudo actualizar desde Jira.";
      setError(message);
    } finally {
      setRefreshing(false);
    }
  }, [view, load]);

  const tags = FILTER_TAGS[view];
  const copy = PAGE_COPY[view];
  const showLeak = view === "OPERATIVAS" || bugType === "ALL";

  const quarterEntries = stats
    ? Object.entries(stats.by_quarter)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([label, value]) => ({ label, value }))
    : [];

  const swfKeysForComposition = stats ? Array.from(new Set(Object.values(stats.swf_by_month).flatMap((m) => Object.keys(m)))) : [];

  return (
    <div className="page page-wide">
      <div className="kpi-page-head">
        <div>
          <p className="eyebrow">{copy.eyebrow}</p>
          <h1>{copy.title}</h1>
          <p className="subtitle">{copy.subtitle}</p>
        </div>
        <div className="kpi-refresh">
          {canRefreshKpis && (
          <button
            type="button"
            className="secondary kpi-refresh-btn"
            onClick={() => void refreshFromJira()}
            disabled={refreshing}
            aria-label="Actualizar desde Jira"
            title="Actualizar desde Jira"
          >
            <RefreshCw size={14} className={refreshing ? "spin" : undefined} aria-hidden="true" />
          </button>
          )}
          <span className="kpi-refresh-meta">
            {refreshing
              ? "Actualizando desde Jira…"
              : refreshSummary
                ? refreshSummary
                : lastUpdated
                  ? `Última actualización ${formatUpdatedAt(lastUpdated)}`
                  : "—"}
          </span>
        </div>
      </div>

      {view === "RELEASE" && (
        <div className="tabnav">
          <button type="button" className={bugType === "QC" ? "active" : ""} onClick={() => setBugType("QC")}>
            QC Bugs
          </button>
          <button type="button" className={bugType === "QA" ? "active" : ""} onClick={() => setBugType("QA")}>
            QA Bugs
          </button>
          <button type="button" className={bugType === "ALL" ? "active" : ""} onClick={() => setBugType("ALL")}>
            QA + QC Bugs
          </button>
        </div>
      )}

      {error && <p className="error-text">{error}</p>}

      {stats && (
        <>
          {/* 1. Volumetría */}
          <div className="kpi-strip">
            <div className="kpi-cell">
              <div className="kpi-num">{stats.total.toLocaleString("es-MX")}</div>
              <div className="kpi-lbl">{view === "OPERATIVAS" ? "Total" : bugType === "ALL" ? "QA + QC Bugs" : bugType === "QC" ? "QC Bugs" : "QA Bugs"}</div>
              <div className="kpi-sub">
                <span className="chip-dot"><span className="dot blocker" />{stats.blocker_count} Blocker</span>
                <span className="chip-dot"><span className="dot critica" />{stats.critical_count} Crítica</span>
                <span className="chip-dot"><span className="dot otros" />{stats.other_count} Otros</span>
              </div>
              <div className="kpi-sub">vía {tags.detected}</div>
            </div>
            <div className="kpi-cell">
              <div className="kpi-num">{stats.open_count.toLocaleString("es-MX")}</div>
              <div className="kpi-lbl">Backlog abierto</div>
              <div className="kpi-sub">{stats.total ? Math.round((stats.open_count / stats.total) * 100) : 0}% del total</div>
            </div>
            {showLeak && (
              <div className="kpi-cell">
                <div className="kpi-num" style={{ color: "var(--kpi-gold)" }}>
                  {view === "RELEASE" && stats.genuine_leak_count !== null
                    ? stats.genuine_leak_count.toLocaleString("es-MX")
                    : stats.leaked_count.toLocaleString("es-MX")}
                </div>
                <div className="kpi-lbl">
                  {view === "RELEASE" ? "Issues levantados hacia FE" : "Fugas reportadas"}
                  {view === "RELEASE" && (
                    <InfoTooltip text="Tickets productivos derivados a un programa de FE que ya pasaron por QC. Se usa como referencia de exposición, no como métrica de precisión absoluta sobre la fuga real." />
                  )}
                </div>
                <div className="kpi-sub">
                  {view === "RELEASE" && stats.genuine_leak_count !== null
                    ? `de ${stats.leaked_count} brutos · ${stats.leak_rate_percent}% · Fuente: Jira ${tags.leaked}`
                    : `${stats.leak_rate_percent}% tasa · vía ${tags.leaked}`}
                </div>
              </div>
            )}
          </div>

          {/* 2. Tendencia mensual */}
          <div className="section-label first">Tendencia mensual</div>
          <div className="panel">
            <div className="panel-header"><h2>Por mes y prioridad</h2></div>
            <div className="panel-body">
              <StackedBarChart data={stats.by_month_priority} categories={PRIORITY_CATEGORIES} colors={PRIORITY_COLORS} isMonthly />
              <p className="chart-footnote">⚽ El Mundial 2026 arranca en abril y alcanza su pico en junio.</p>
            </div>
          </div>

          {/* 3. Distribución */}
          <div className="section-label">Distribución</div>
          <div className="grid-two">
            <div className="panel">
              <div className="panel-header"><h2>Por SWF</h2></div>
              <div className="panel-body">
                <DonutChart items={sortedEntries(stats.by_swf)} />
              </div>
            </div>
            {view === "OPERATIVAS" ? (
              <div className="panel">
                <div className="panel-header"><h2>Por Cluster</h2></div>
                <div className="panel-body">
                  <p className="panel-subtitle">
                    Campo Cluster de Jira (población completa)
                    <InfoTooltip text="Andina/Dominicana se separa según el país mencionado en el resumen del ticket." />
                  </p>
                  <BarList items={sortedEntries(stats.by_cluster)} color="var(--kpi-teal)" />
                </div>
              </div>
            ) : (
              <div className="panel">
                <div className="panel-header"><h2>Por trimestre</h2></div>
                <div className="panel-body">
                  <BarList items={quarterEntries} color="var(--kpi-blue)" />
                </div>
              </div>
            )}
          </div>

          {/* 4. Backlog */}
          <div className="section-label">Backlog</div>
          <div className="grid-two">
            <div className="panel">
              <div className="panel-header"><h2>Backlog abierto</h2></div>
              <div className="panel-body">
                <DonutChart items={sortedEntries(stats.open_by_priority)} colors={PRIORITY_COLORS} />
              </div>
            </div>
            <div className="panel">
              <div className="panel-header"><h2>Backlog por estado</h2></div>
              <div className="panel-body">
                <BarList items={sortedEntries(stats.by_status)} color="var(--kpi-blue)" />
              </div>
            </div>
          </div>

          {/* 5-6. Release only: Severidad por SWF / Composición de SWF por mes */}
          {view === "RELEASE" && (
            <>
              <div className="section-label">
                Severidad por SWF
                <InfoTooltip text="Porcentaje de Blocker, Crítica y Otros dentro del total de cada SWF; no representa volumen absoluto." />
              </div>
              <div className="panel">
                <div className="panel-header"><h2>% por SWF</h2></div>
                <div className="panel-body">
                  <StackedBarChart data={stats.severity_by_swf} categories={PRIORITY_CATEGORIES} colors={PRIORITY_COLORS} fullHeight />
                </div>
              </div>

              <div className="section-label">
                Composición de SWF por mes
                <InfoTooltip text="Cómo varía la carga entre software factories a lo largo del año." />
              </div>
              <div className="panel">
                <div className="panel-header"><h2>SWF por mes</h2></div>
                <div className="panel-body">
                  <StackedBarChart data={stats.swf_by_month} categories={swfKeysForComposition} isMonthly />
                </div>
              </div>
            </>
          )}

          {/* 7. Top dispositivos */}
          <div className="section-label">{view === "OPERATIVAS" ? "Por dispositivo / programa" : "Top dispositivos"}</div>
          <div className="panel">
            <div className="panel-header"><h2>{view === "OPERATIVAS" ? "Por dispositivo / programa" : "Top 15 dispositivo / programa"}</h2></div>
            <div className="panel-body">
              <BarList
                items={view === "RELEASE" ? sortedEntries(stats.by_device).slice(0, 15) : sortedEntries(stats.by_device)}
                color="var(--kpi-blue)"
              />
            </div>
          </div>

          {/* 8. Fuga de defectos -- always last; only shown in Operativa or Release's QA+QC view */}
          {showLeak && (
            <>
              <div className="section-label">
                Fuga de defectos
                <InfoTooltip text="Tickets levantados después de que QC concluyó su revisión y antes de Producción. Se considera fuga porque QC no lo detectó, aunque fue identificado antes de llegar a Producción." />
              </div>
              <div className="panel">
                <div className="panel-header"><h2>Por mes (total y tasa)</h2></div>
                <div className="panel-body">
                  <LeakTrendChart data={stats.leak_by_month} />
                </div>
              </div>

              {view === "RELEASE" && (
                <div className="grid-two" style={{ marginTop: "14px" }}>
                  <div className="panel">
                    <div className="panel-header"><h2>Fuga por SWF</h2></div>
                    <div className="panel-body">
                      <BarList items={sortedEntries(stats.leak_by_swf)} color="var(--kpi-gold)" />
                    </div>
                  </div>
                  <div className="panel">
                    <div className="panel-header"><h2>Fuga por proyecto</h2></div>
                    <div className="panel-body">
                      <BarList items={sortedEntries(stats.leak_by_project)} color="var(--kpi-gold)" />
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}
