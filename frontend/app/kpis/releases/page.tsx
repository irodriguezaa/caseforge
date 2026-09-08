"use client";

import { useEffect, useMemo, useState } from "react";
import { BarList } from "@/app/components/BarList";
import { StackedBarChart } from "@/app/components/StackedBarChart";
import { api } from "@/lib/api";
import { monthFullName } from "@/lib/kpiDashboard";
import type { ReleaseKpisRead } from "@/lib/types";

const VOLUME_CATEGORIES = ["Release App", "Release BE", "Operativas"] as const;
const VOLUME_COLORS: Record<string, string> = {
  "Release App": "var(--kpi-blue)",
  "Release BE": "var(--kpi-teal)",
  Operativas: "var(--kpi-gray)",
};

export default function KpisReleasesPage(): React.ReactElement {
  const [data, setData] = useState<ReleaseKpisRead | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getReleaseKpis()
      .then(setData)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Error"));
  }, []);

  const volumeByMonth = useMemo(() => {
    const chart: Record<string, Record<string, number>> = {};
    for (const row of data?.by_month ?? []) {
      chart[row.month] = {
        "Release App": row.app,
        "Release BE": row.be,
        Operativas: row.operativa,
      };
    }
    return chart;
  }, [data]);

  return (
    <div className="page page-wide">
      <div className="kpi-page-head">
        <div>
          <p className="eyebrow">KPIs · Releases</p>
          <h1>KPIs de Releases</h1>
          <p className="subtitle">
            Volumen de ciclos QC. No cancelados. El mes es la fecha de creación del Release.
          </p>
        </div>
      </div>

      {error && <p className="error-text">No se pudo cargar el tablero: {error}</p>}

      {data && (
        <>
          <div className="metrics-row metrics-row-volume">
            <div className="metric-cell">
              <div className="metric-label">Total Releases</div>
              <div className="metric-value">{data.total}</div>
            </div>
            <div className="metric-cell">
              <div className="metric-label">Release App</div>
              <div className="metric-value">{data.app}</div>
            </div>
            <div className="metric-cell">
              <div className="metric-label">Release BE</div>
              <div className="metric-value">{data.be}</div>
            </div>
            <div className="metric-cell">
              <div className="metric-label">Operativas</div>
              <div className="metric-value">{data.operativa}</div>
            </div>
          </div>

          <div className="panel">
            <div className="panel-header">
              <h2>Evolución mensual de Releases</h2>
            </div>
            <div className="panel-body">
              <StackedBarChart
                data={volumeByMonth}
                categories={[...VOLUME_CATEGORIES]}
                colors={VOLUME_COLORS}
                formatLabel={monthFullName}
              />
            </div>
          </div>

          <div className="panel">
            <div className="panel-header">
              <h2>Participaciones QC por Cluster</h2>
            </div>
            <div className="panel-body">
              <p className="kpi-volume-caption">
                Cada Release cuenta una vez por cada Cluster donde QC debe realizar la validación.
              </p>
              <div className="metrics-row metrics-row-cluster">
                <div className="metric-cell">
                  <div className="metric-label">Validaciones regionales</div>
                  <div className="metric-value">{data.cluster_validations_total}</div>
                  <div className="metric-caption">Puede ser mayor que el total de Releases</div>
                </div>
                <div className="metric-cell">
                  <div className="metric-label">Promedio de clusters por Release</div>
                  <div className="metric-value">{data.clusters_per_release_avg.toFixed(2)}</div>
                  <div className="metric-caption">Validaciones / Releases</div>
                </div>
              </div>
              <BarList
                items={[...data.by_cluster]
                  .sort((a, b) => b.count - a.count)
                  .map((row) => ({ label: row.cluster, value: row.count }))}
                color="var(--kpi-teal)"
              />
            </div>
          </div>

          <div className="panel">
            <div className="panel-header">
              <h2>Release Apps por Entregable y Versiones</h2>
            </div>
            <div className="panel-body">
              <p className="kpi-volume-caption">
                Muestra los ciclos QC y versiones de los Entregables de Release App. BE y
                Operativas no participan en este indicador.
              </p>
              <table className="activity kpi-deliverable-table">
                <thead>
                  <tr>
                    <th>Entregable</th>
                    <th className="num">Releases QC</th>
                    <th className="num">Versiones</th>
                  </tr>
                </thead>
                <tbody>
                  {data.by_deliverable.map((row) => (
                    <tr
                      key={
                        row.deliverable_id != null
                          ? `d-${row.deliverable_id}`
                          : "sin-entregable"
                      }
                    >
                      <td>{row.deliverable_name}</td>
                      <td className="num">{row.releases}</td>
                      <td className="num">{row.versions == null ? "N/A" : row.versions}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="panel">
            <div className="panel-header">
              <h2>Distribución de Releases por SWF</h2>
            </div>
            <div className="panel-body">
              <p className="kpi-volume-caption">
                App se clasifica por dispositivo. BE usa el SWF persistido. Operativas no
                tienen SWF y quedan fuera.
              </p>
              <div className="metrics-row metrics-row-swf">
                <div className="metric-cell">
                  <div className="metric-label">Releases considerados</div>
                  <div className="metric-value">{data.swf.considered}</div>
                  <div className="metric-caption">App + BE. Sin Operativas</div>
                </div>
                {data.swf.unclassified > 0 && (
                  <div className="metric-cell">
                    <div className="metric-label">No clasificables</div>
                    <div className="metric-value">{data.swf.unclassified}</div>
                    <div className="metric-caption">Plataforma o SWF BE ausente</div>
                  </div>
                )}
              </div>
              <BarList
                items={data.swf.by_swf.map((row) => ({ label: row.swf, value: row.releases }))}
                color="var(--kpi-blue)"
              />
              <table className="activity kpi-deliverable-table" style={{ marginTop: "12px" }}>
                <thead>
                  <tr>
                    <th>SWF</th>
                    <th className="num">Releases QC</th>
                    <th className="num">Participación</th>
                  </tr>
                </thead>
                <tbody>
                  {data.swf.by_swf.map((row) => (
                    <tr key={row.swf}>
                      <td>{row.swf}</td>
                      <td className="num">{row.releases}</td>
                      <td className="num">{row.percent}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {data.swf.unclassified_rows.length > 0 && (
                <table className="activity kpi-deliverable-table" style={{ marginTop: "12px" }}>
                  <thead>
                    <tr>
                      <th>No clasificable</th>
                      <th>Origen</th>
                      <th className="num">Releases</th>
                      <th>Causa</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.swf.unclassified_rows.map((row) => (
                      <tr key={`${row.origin}-${row.platform ?? "none"}-${row.reason}`}>
                        <td>{row.platform ?? "—"}</td>
                        <td>{row.origin}</td>
                        <td className="num">{row.count}</td>
                        <td>{row.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>

          <div className="panel">
            <div className="panel-header">
              <h2>Revalidaciones</h2>
            </div>
            <div className="panel-body">
              <p className="kpi-volume-caption">
                Solo Release App, según el tipo persistido (Nuevo / Revalidación). BE y
                Operativas no tienen este campo.
              </p>
              <div className="metrics-row metrics-row-reval">
                <div className="metric-cell">
                  <div className="metric-label">Total Releases</div>
                  <div className="metric-value">{data.revalidation.total}</div>
                  <div className="metric-caption">Universo KPI</div>
                </div>
                <div className="metric-cell">
                  <div className="metric-label">Releases Nuevos</div>
                  <div className="metric-value">{data.revalidation.nuevo}</div>
                  <div className="metric-caption">Release App</div>
                </div>
                <div className="metric-cell">
                  <div className="metric-label">Revalidaciones</div>
                  <div className="metric-value">{data.revalidation.revalidacion}</div>
                  <div className="metric-caption">Release App</div>
                </div>
                <div className="metric-cell">
                  <div className="metric-label">% Revalidación</div>
                  <div className="metric-value">{data.revalidation.revalidacion_percent}%</div>
                  <div className="metric-caption">Sobre Releases App ({data.revalidation.app})</div>
                </div>
              </div>
              <BarList
                items={[
                  { label: "Nuevo", value: data.revalidation.nuevo },
                  { label: "Revalidación", value: data.revalidation.revalidacion },
                ]}
                color="var(--kpi-gold)"
              />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
