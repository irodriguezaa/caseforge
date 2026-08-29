"use client";

import { ListChecks } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { RiskBadge } from "@/app/components/RiskBadge";
import { StatusBadge } from "@/app/components/StatusBadge";
import { api } from "@/lib/api";
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

export default function DashboardPage(): React.ReactElement {
  const router = useRouter();

  const [summary, setSummary] = useState<QcDashboardSummary | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [releases, setReleases] = useState<Release[]>([]);

  // "" means "Todos" (no filter applied) for all three -- this is the default on load, so the
  // Dashboard shows the global view immediately instead of an arbitrarily narrow slice.
  const [month, setMonth] = useState<string>("");
  const [cluster, setCluster] = useState<string>("");
  const [releaseId, setReleaseId] = useState<string>("");

  const [system, setSystem] = useState<{ backend: CheckStatus; database: CheckStatus }>({
    backend: "idle",
    database: "idle",
  });

  useEffect(() => {
    api.listReleases().then(setReleases).catch(() => setReleases([]));
  }, []);

  const loadSummary = useCallback((): void => {
    const filters: QcSummaryFilters = {};
    if (month) filters.month = `${CURRENT_YEAR}-${month}`;
    if (cluster) filters.cluster = cluster;
    if (releaseId) filters.release_id = Number(releaseId);
    api
      .getQcSummary(filters)
      .then(setSummary)
      .catch((err: unknown) => setSummaryError(err instanceof Error ? err.message : "Error"));
  }, [month, cluster, releaseId]);

  useEffect(loadSummary, [loadSummary]);

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
    const [backend, database] = await Promise.all([check("/api/health"), check("/api/health/db")]);
    setSystem({ backend, database });
  }, []);

  useEffect(() => {
    void checkConnection();
  }, [checkConnection]);

  const filteredReleases = releases.filter((r) => {
    if (cluster && r.cluster !== cluster && r.cluster !== "Todos") return false;
    if (releaseId && String(r.id) !== releaseId) return false;
    return true;
  });
  const releasesTotal = filteredReleases.length;
  const releasesInProgress = filteredReleases.filter((r) => r.status === "IN_PROGRESS").length;

  const activeItems = summary?.active_items ?? [];

  return (
    <div className="page page-wide">
      <div className="dashboard-header">
        <div className="page-header" style={{ marginBottom: 0 }}>
          <h1>Actividades QC en curso</h1>
          <p className="subtitle">
            {(releases.find((r) => String(r.id) === releaseId)?.name) ?? "Todos"} · {cluster || "Todos"} · {MONTHS.find((m) => m.value === month)?.label ?? "Todos"}
          </p>
        </div>
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
            {releases.map((r) => (
              <option key={r.id} value={r.id}>{r.name} v{r.version}</option>
            ))}
          </select>
        </div>
      </div>

      {summaryError && <p className="error-text">No se pudo cargar el resumen: {summaryError}</p>}

      {summary && (
        <>
          <div className="metrics-row metrics-row-compact">
            <div className="metric-cell">
              <div className="metric-label">Releases</div>
              <div className="metric-value">{releasesTotal}</div>
            </div>
            <div className="metric-cell">
              <div className="metric-label">En curso</div>
              <div className="metric-value">{releasesInProgress}</div>
            </div>
            <div className="metric-cell">
              <div className="metric-label"><ListChecks size={12} aria-hidden="true" />Total de Cases</div>
              <div className="metric-value">{summary.test_cases_planned}</div>
            </div>
          </div>

          <div className="panel">
            <div className="panel-header">
              <h2>Actividades QC en curso</h2>
              <a href="/releases" className="panel-action">Ver todas las releases →</a>
            </div>
            <div className="panel-body no-pad">
              <table className="activity">
                <thead>
                  <tr>
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
                  {activeItems.map((item) => (
                    <tr
                      key={item.release_id}
                      className="clickable"
                      onClick={() => router.push(`/releases/${item.release_id}`)}
                      title="Ver detalle de la Release"
                    >
                      <td style={{ fontWeight: 500 }}>{item.release_name} v{item.release_version}</td>
                      <td className="muted">
                        {item.window_start_date && item.window_end_date
                          ? `${formatDate(item.window_start_date)} – ${formatDate(item.window_end_date)}`
                          : "Sin fecha"}
                      </td>
                      <td className="muted">{item.cluster ?? "—"}</td>
                      <td className="muted">{item.platform}</td>
                      <td>{item.percent_avance.toFixed(0)}%</td>
                      <td>{item.percent_cobertura.toFixed(0)}%</td>
                      <td><StatusBadge status={item.status} /></td>
                      <td className={item.defects_blocker_count > 0 ? "danger-text" : "muted"}>{item.defects_blocker_count}</td>
                      <td><RiskBadge level={item.risk_level} /></td>
                    </tr>
                  ))}
                  {activeItems.length === 0 && (
                    <tr><td colSpan={9} className="muted">No hay actividades de QC en curso para este filtro.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="panel">
            <div className="panel-header"><h2>Ejecución por Release</h2></div>
            <div className="panel-body">
              {activeItems.map((item) => {
                const total = item.pass_count + item.fail_count + item.blocked_count + item.unexecuted_count;
                const pct = (n: number) => (total ? (n / total) * 100 : 0);
                return (
                  <div className="exec-release-block" key={item.release_id}>
                    <div className="exec-release-title">
                      {item.release_name} v{item.release_version}
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
              {activeItems.length === 0 && <p className="muted">No hay actividad para este filtro.</p>}
            </div>
          </div>
        </>

      )}

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
