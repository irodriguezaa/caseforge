"use client";

import { useEffect, useMemo, useState } from "react";
import { ExecutivePieChart } from "@/app/components/ExecutivePieChart";
import { ExecutionPriorityBars } from "@/app/components/ExecutionPriorityBars";
import { GroupedStackedBars } from "@/app/components/GroupedStackedBars";
import { api } from "@/lib/api";
import type { SprintTestingOptions, SprintTestingRead } from "@/lib/types";

export default function SprintTestingPage(): React.ReactElement {
  const [options, setOptions] = useState<SprintTestingOptions | null>(null);
  const [sprint, setSprint] = useState("44");
  const [swf, setSwf] = useState("hitss");
  const [data, setData] = useState<SprintTestingRead | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exportingIssues, setExportingIssues] = useState(false);
  const [exportingReport, setExportingReport] = useState(false);

  useEffect(() => {
    api
      .getSprintTestingOptions()
      .then((body) => {
        setOptions(body);
        const first = body.sprints.find((item) => item.actionable) ?? body.sprints[0];
        if (first) setSprint(first.id);
        if (body.swfs[0]) setSwf(body.swfs[0].id);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Error"));
  }, []);

  const selectedSprint = options?.sprints.find((item) => item.id === sprint);
  const canQuery = Boolean(selectedSprint?.actionable);

  useEffect(() => {
    if (!canQuery) {
      setData(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .getSprintTesting(sprint, swf)
      .then((body) => {
        if (!cancelled) setData(body);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setData(null);
          setError(err instanceof Error ? err.message : "Error");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sprint, swf, canQuery]);

  const totals = useMemo(() => {
    const open = data?.programs.reduce((sum, row) => sum + row.open, 0) ?? 0;
    const closed = data?.programs.reduce((sum, row) => sum + row.closed_total, 0) ?? 0;
    return { open, closed };
  }, [data]);

  async function handleExportIssues(): Promise<void> {
    setExportingIssues(true);
    setError(null);
    try {
      await api.exportSprintTestingIssues(sprint, swf);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "No se pudo extraer la información.");
    } finally {
      setExportingIssues(false);
    }
  }

  async function handleExportReport(): Promise<void> {
    setExportingReport(true);
    setError(null);
    try {
      await api.exportSprintTestingReport(sprint, swf);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "No se pudo generar el reporte ejecutivo.");
    } finally {
      setExportingReport(false);
    }
  }

  return (
    <div className="page page-wide">
      <div className="kpi-page-head">
        <div>
          <p className="eyebrow">Operación</p>
          <h1>Sprint Testing</h1>
          <p className="subtitle">Avance de Technical Epics del Sprint en Jira, por SWF.</p>
        </div>
      </div>

      <div
        className="filter-bar"
        style={{ marginBottom: "16px", display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}
      >
        <label className="muted" style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          Sprint
          <select value={sprint} onChange={(event) => setSprint(event.target.value)}>
            {(options?.sprints ?? []).map((item) => (
              <option key={item.id} value={item.id} disabled={!item.actionable}>
                {item.label}
                {item.actionable ? "" : " (filtro pendiente)"}
              </option>
            ))}
          </select>
        </label>
        <label className="muted" style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          SWF
          <select value={swf} onChange={(event) => setSwf(event.target.value)}>
            {(options?.swfs ?? []).map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          disabled={!canQuery || loading || exportingReport}
          onClick={() => void handleExportReport()}
          style={{ marginLeft: "auto" }}
        >
          {exportingReport ? "Generando..." : "Reporte ejecutivo"}
        </button>
      </div>

      {!canQuery && (
        <p className="muted">Este Sprint aún no tiene un Saved Filter de Jira configurado.</p>
      )}
      {error && <p className="error-text">{error}</p>}
      {loading && <p className="muted">Cargando información de Jira...</p>}

      {!loading && canQuery && data && data.programs.length === 0 && !data.execution?.programs.length && (
        <p className="muted">No hay Technical Epics ni issues de ejecución para este Sprint y SWF.</p>
      )}

      {!loading && data && data.programs.length > 0 && (
        <>
          <div className="metrics-row metrics-row-volume">
            <div className="metric-cell">
              <div className="metric-label">Technical Epics</div>
              <div className="metric-value">{data.technical_epic_count}</div>
            </div>
            <div className="metric-cell">
              <div className="metric-label">Abiertos</div>
              <div className="metric-value">{totals.open}</div>
            </div>
            <div className="metric-cell">
              <div className="metric-label">Cerrados</div>
              <div className="metric-value">{totals.closed}</div>
            </div>
            <div className="metric-cell">
              <div className="metric-label">SWF</div>
              <div className="metric-value" style={{ fontSize: "16px" }}>
                {data.swf}
              </div>
            </div>
          </div>

          <div className="panel">
            <div className="panel-header">
              <h2>Estado de Technical Epics</h2>
            </div>
            <div className="panel-body">
              <p className="muted" style={{ marginTop: 0 }}>
                Se muestra el estado de las Technical Epics por dispositivo, cada segmento es el estado real de
                Jira.
              </p>
              <GroupedStackedBars programs={data.programs} />
            </div>
          </div>

          <div className="panel" style={{ marginTop: "14px" }}>
            <div className="panel-header">
              <h2>Abiertos vs cerrados</h2>
            </div>
            <div className="panel-body">
              <p className="muted" style={{ marginTop: 0, marginBottom: 4 }}>
                Abierto + cerrado = total de Technical Epics del programa.
              </p>
              <p className="muted" style={{ marginTop: 0, fontSize: "11px" }}>
                Filtro Jira: {data.sprint.filter_id}
              </p>
              <ExecutivePieChart open={totals.open} closed={totals.closed} programs={data.programs} />
            </div>
          </div>
        </>
      )}

      {!loading && data && data.execution && (
        <div className="panel" style={{ marginTop: "14px" }}>
          <div className="panel-header">
            <h2>Issues del Sprint en ejecución</h2>
            <button
              type="button"
              className="secondary"
              disabled={exportingIssues}
              onClick={() => void handleExportIssues()}
            >
              {exportingIssues ? "Extrayendo..." : "Extraer información"}
            </button>
          </div>
          <div className="panel-body">
            <p className="muted" style={{ marginTop: 0, marginBottom: 4 }}>
              Issues del Sprint en curso, por dispositivo: Blocker vs no Blocker.
            </p>
            <p className="muted" style={{ marginTop: 0, fontSize: "11px" }}>
              Filtro Jira: {data.execution.filter_id}
            </p>
            {data.execution.programs.length === 0 ? (
              <p className="muted">No hay issues de ejecución para este SWF.</p>
            ) : (
              <ExecutionPriorityBars programs={data.execution.programs} />
            )}
          </div>
        </div>
      )}
      {!loading && data && !data.execution && canQuery && (
        <div className="panel" style={{ marginTop: "14px" }}>
          <div className="panel-header">
            <h2>Issues del Sprint en ejecución</h2>
          </div>
          <div className="panel-body">
            <p className="muted" style={{ marginTop: 0 }}>
              Este Sprint aún no tiene un Saved Filter de issues en ejecución.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
