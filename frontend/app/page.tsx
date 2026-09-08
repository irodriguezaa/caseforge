"use client";

import { ListChecks } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { QcCalendarView } from "@/app/components/QcCalendarView";
import { RiskBadge } from "@/app/components/RiskBadge";
import { StatusBadge } from "@/app/components/StatusBadge";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { CLUSTERS, MONTHS } from "@/lib/constants";
import type { QcDashboardSummary, QcSummaryFilters, Release } from "@/lib/types";
import { useRouter } from "next/navigation";

type CheckStatus = "idle" | "loading" | "ok" | "error";

interface HealthResponse {
  status: string;
  service: string;
  message?: string;
}

const healthCheckTimeoutMs = 5_000;
const CURRENT_YEAR = new Date().getFullYear();

function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
}

const ORIGIN_LABEL: Record<"APP" | "BE" | "OPERATIVA", string> = {
  APP: "Release App",
  BE: "Release BE",
  OPERATIVA: "Operativa",
};

function deviceLabel(item: { origin_kind: "APP" | "BE" | "OPERATIVA"; platform: string }): string {
  if (item.origin_kind === "BE" || item.origin_kind === "OPERATIVA") return "Todos/Segmentado";
  return item.platform;
}

function clusterLabel(item: { origin_kind: "APP" | "BE" | "OPERATIVA"; cluster: string | null }): string {
  if (item.origin_kind === "BE") return "—";
  return item.cluster ?? "—";
}

function releaseFilterLabel(r: Release): string {
  if (r.be_release_id) return `${r.name} (BE)`;
  if (r.operativa_release_id) return `${r.name} (Operativa)`;
  return `${r.name} v${r.version}`;
}

function activityReleaseLabel(item: {
  origin_kind: "APP" | "BE" | "OPERATIVA";
  release_name: string;
  release_version: string;
}): string {
  if (item.origin_kind === "BE") return `${item.release_name} (BE)`;
  if (item.origin_kind === "OPERATIVA") return `${item.release_name} (Operativa)`;
  return `${item.release_name} v${item.release_version}`;
}

function formatUpdatedAt(date: Date): string {
  return date.toLocaleString("es-MX", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function DashboardPage(): React.ReactElement {
  const router = useRouter();
  const { canSeeReleases } = useAuth();

  const [summary, setSummary] = useState<QcDashboardSummary | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [releases, setReleases] = useState<Release[]>([]);

  // "" means "Todos" (no filter applied) for all three -- this is the default on load, so the
  // Dashboard shows the global view immediately instead of an arbitrarily narrow slice.
  const [month, setMonth] = useState<string>("");
  const [cluster, setCluster] = useState<string>("");
  const [releaseId, setReleaseId] = useState<string>("");
  const [execStatus, setExecStatus] = useState<string>("IN_PROGRESS");

  const [system, setSystem] = useState<{ backend: CheckStatus; database: CheckStatus }>({
    backend: "idle",
    database: "idle",
  });
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  useEffect(() => {
    if (!canSeeReleases) {
      setReleases([]);
      return;
    }
    api.listReleases({ include_be: true, include_operativa: true }).then(setReleases).catch(() => setReleases([]));
  }, [canSeeReleases]);

  const loadSummary = useCallback((): void => {
    const filters: QcSummaryFilters = {};
    if (month) filters.month = `${CURRENT_YEAR}-${month}`;
    if (cluster) filters.cluster = cluster;
    if (releaseId) filters.release_id = Number(releaseId);
    api
      .getQcSummary(filters)
      .then((data) => {
        setSummary(data);
        setLastUpdated(new Date());
      })
      .catch((err: unknown) => setSummaryError(err instanceof Error ? err.message : "Error"));
  }, [month, cluster, releaseId]);

  useEffect(loadSummary, [loadSummary]);

  useEffect(() => {
    setLastUpdated(new Date());
    const id = window.setInterval(() => setLastUpdated(new Date()), 60_000);
    return () => window.clearInterval(id);
  }, []);

  const checkConnection = useCallback(async (): Promise<void> => {
    setSystem({ backend: "loading", database: "loading" });
    const check = async (path: string): Promise<CheckStatus> => {
      try {
        const response = await fetch(path, { cache: "no-store", signal: AbortSignal.timeout(healthCheckTimeoutMs) });
        const payload = (await response.json()) as HealthResponse;
        return response.ok && payload.status === "ok" ? "ok" : "error";
      } catch {
        return "error";
      }
    };
    const [backend, database] = await Promise.all([
      check("/qcpulse/api/health"),
      check("/qcpulse/api/health/db"),
    ]);
    setSystem({ backend, database });
  }, []);

  useEffect(() => {
    void checkConnection();
  }, [checkConnection]);

  const statusFilteredItems = (summary?.execution_items ?? summary?.active_items ?? []).filter((item) =>
    execStatus ? item.status === execStatus : true
  );

  const releaseOptions = useMemo(() => {
    if (releases.length > 0) {
      return releases.map((row) => ({ id: row.id, label: releaseFilterLabel(row) }));
    }
    const labels = new Map<number, string>();
    for (const item of summary?.execution_items ?? []) {
      if (!labels.has(item.release_id)) {
        labels.set(item.release_id, activityReleaseLabel(item));
      }
    }
    return [...labels.entries()].map(([id, label]) => ({ id, label }));
  }, [releases, summary]);

  // "Agosto 2026" when a month is picked; "Todos los periodos" when the filter is "Todos" --
  // purely descriptive, does not change test_cases_planned's formula at all.
  const totalCasesPeriodLabel = month
    ? `${MONTHS.find((m) => m.value === month)?.label} ${CURRENT_YEAR}`
    : "Todos los periodos";

  return (
    <div className="page page-wide">
      <div className="qc-masthead">
        <div>
          <p className="qc-masthead-title">QC Control Center</p>
          <p className="qc-masthead-sub">Operación de Calidad · Claro video</p>
        </div>
        <div className="qc-masthead-meta">
          <div className="qc-masthead-meta-label">Última actualización</div>
          {lastUpdated ? (
            <time className="qc-masthead-meta-value" dateTime={lastUpdated.toISOString()}>
              {formatUpdatedAt(lastUpdated)}
            </time>
          ) : (
            <span className="qc-masthead-meta-value">—</span>
          )}
        </div>
      </div>

      <div className="dashboard-header">
        <p className="dashboard-filter-context">
          {(releaseOptions.find((row) => String(row.id) === releaseId)?.label) ?? "Todos"} · {cluster || "Todos"} · {MONTHS.find((m) => m.value === month)?.label ?? "Todos"}
        </p>
        <div className="filter-bar">
          <select value={month} onChange={(e) => setMonth(e.target.value)}>
            <option value="">Todos</option>
            {MONTHS.map((m) => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </select>
          <select value={cluster} onChange={(e) => setCluster(e.target.value)}>
            <option value="">Todos</option>
            {CLUSTERS.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
          <select value={releaseId} onChange={(e) => setReleaseId(e.target.value)}>
            <option value="">Todos</option>
            {releaseOptions.map((row) => (
              <option key={row.id} value={row.id}>{row.label}</option>
            ))}
          </select>
        </div>
      </div>

      {summaryError && <p className="error-text">No se pudo cargar el resumen: {summaryError}</p>}

      {summary && (
        <>
          <div className="metrics-row metrics-row-compact">
            <div className="metric-cell">
              <div className="metric-label">Total</div>
              <div className="metric-value">{summary.in_progress_total}</div>
            </div>
            <div className="metric-cell">
              <div className="metric-label">En curso Release App</div>
              <div className="metric-value">{summary.in_progress_app}</div>
            </div>
            <div className="metric-cell">
              <div className="metric-label">En curso Release BE</div>
              <div className="metric-value">{summary.in_progress_be}</div>
            </div>
            <div className="metric-cell">
              <div className="metric-label">En curso Operativas</div>
              <div className="metric-value">{summary.in_progress_operativa}</div>
            </div>
            <div className="metric-cell">
              <div className="metric-label"><ListChecks size={12} aria-hidden="true" />Total de Cases</div>
              <div className="metric-value">{summary.test_cases_planned}</div>
              <div className="metric-caption">{totalCasesPeriodLabel}</div>
            </div>
          </div>

          <div className="panel">
            <div className="panel-header">
              <h2>Actividades QC en curso</h2>
              <div className="filter-bar">
                <select
                  aria-label="Filtrar por estado"
                  value={execStatus}
                  onChange={(e) => setExecStatus(e.target.value)}
                >
                  <option value="IN_PROGRESS">IN PROGRESS</option>
                  <option value="DRAFT">DRAFT</option>
                  <option value="COMPLETED">COMPLETED</option>
                  <option value="CANCELLED">CANCELLED</option>
                  <option value="">Todos</option>
                </select>
              </div>
            </div>
            <div className="panel-body no-pad">
              <table className="activity">
                <thead>
                  <tr>
                    <th>Tipo</th>
                    <th>Release</th>
                    <th>Fecha</th>
                    <th>Cluster</th>
                    <th>Dispositivo</th>
                    <th>% Avance</th>
                    <th>% Cobertura</th>
                    <th>Estado</th>
                    <th>Blocker</th>
                    <th>Nivel de riesgo</th>
                  </tr>
                </thead>
                <tbody>
                  {statusFilteredItems.map((item) => (
                    <tr
                      key={item.release_id}
                      className={canSeeReleases ? "clickable" : undefined}
                      onClick={canSeeReleases ? () => router.push(`/releases/${item.release_id}`) : undefined}
                      title={canSeeReleases ? "Ver detalle de la Release" : undefined}
                    >
                      <td className="muted">{ORIGIN_LABEL[item.origin_kind]}</td>
                      <td style={{ fontWeight: 500 }}>{item.release_name} v{item.release_version}</td>
                      <td className="muted">
                        {item.window_start_date && item.window_end_date
                          ? `${formatDate(item.window_start_date)} – ${formatDate(item.window_end_date)}`
                          : "Sin fecha"}
                      </td>
                      <td className="muted">{clusterLabel(item)}</td>
                      <td className="muted">{deviceLabel(item)}</td>
                      <td>{item.percent_avance.toFixed(0)}%</td>
                      <td>{item.percent_cobertura.toFixed(0)}%</td>
                      <td><StatusBadge status={item.status} /></td>
                      <td className={item.defects_blocker_count > 0 ? "danger-text" : "muted"}>{item.defects_blocker_count}</td>
                      <td><RiskBadge level={item.risk_level} /></td>
                    </tr>
                  ))}
                  {statusFilteredItems.length === 0 && (
                    <tr>
                      <td colSpan={10} className="muted">
                        {execStatus
                          ? `No hay actividades en ${execStatus.replace("_", " ")} para este filtro.`
                          : "No hay actividades de QC para este filtro."}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="panel">
            <div className="panel-header">
              <h2>Ejecución por Release</h2>
            </div>
            <div className="panel-body">
              {statusFilteredItems.map((item) => {
                const total = item.pass_count + item.fail_count + item.blocked_count + item.unexecuted_count;
                const pct = (n: number) => (total ? (n / total) * 100 : 0);
                return (
                  <div className="exec-release-block" key={item.release_id}>
                    <div className="exec-release-title">
                      <span>
                        {item.release_name} v{item.release_version}
                        <span className="exec-release-deliverable"> · {ORIGIN_LABEL[item.origin_kind]}</span>
                        {item.deliverable_name && (
                          <span className="exec-release-deliverable">
                            {" "}· {item.deliverable_name}
                            {item.release_type === "REVALIDACION" ? " · Revalidación" : item.release_type === "NUEVO" ? " · Nuevo" : ""}
                            {item.deliverable_release_ordinal != null && item.deliverable_total_versions != null && (
                              <> (v{item.deliverable_release_ordinal} de {item.deliverable_total_versions}
                                {item.deliverable_total_revalidaciones ? ` · ${item.deliverable_total_revalidaciones} revalidacion${item.deliverable_total_revalidaciones === 1 ? "" : "es"}` : ""})
                              </>
                            )}
                          </span>
                        )}
                      </span>
                      <span className="exec-release-pct">{item.percent_avance.toFixed(0)}% ejecutado</span>
                    </div>
                    <div className="exec-numbers">
                      <div className="exec-item"><div className="exec-label">Planned</div><div className="exec-value">{item.planned}</div></div>
                      <div className="exec-item"><div className="exec-label">Executed</div><div className="exec-value">{item.executed}</div></div>
                      <div className="exec-item pass"><div className="exec-label">Pass</div><div className="exec-value">{item.pass_count}</div></div>
                      <div className="exec-item fail"><div className="exec-label">Fail</div><div className="exec-value">{item.fail_count}</div></div>
                      <div className="exec-item blocked"><div className="exec-label">Blocked</div><div className="exec-value">{item.blocked_count}</div></div>
                      <div className="exec-item"><div className="exec-label">Unexecuted</div><div className="exec-value">{item.unexecuted_count}</div></div>
                    </div>
                    <div className="exec-bar wide">
                      <div className="seg-pass" style={{ width: `${pct(item.pass_count)}%` }} />
                      <div className="seg-fail" style={{ width: `${pct(item.fail_count)}%` }} />
                      <div className="seg-blocked" style={{ width: `${pct(item.blocked_count)}%` }} />
                      <div className="seg-unexecuted" style={{ width: `${pct(item.unexecuted_count)}%` }} />
                    </div>
                  </div>
                );
              })}
              {statusFilteredItems.length === 0 && (
                <p className="muted">
                  {execStatus
                    ? `No hay releases en ${execStatus.replace("_", " ")} para este filtro.`
                    : "No hay actividad para este filtro."}
                </p>
              )}
            </div>
          </div>
        </>

      )}

      <QcCalendarView />

      <div className="system-health-line">
        <span>System health</span>
        <span className="sh-item"><span className={`sh-dot ${system.backend}`} /> Backend</span>
        <span className="sh-item"><span className={`sh-dot ${system.database}`} /> Database</span>
        <span className="sh-item"><span className="sh-dot ok" /> Frontend</span>
        <button type="button" className="secondary" onClick={checkConnection} style={{ marginLeft: "auto" }}>
          Comprobar
        </button>
      </div>
    </div>
  );
}
