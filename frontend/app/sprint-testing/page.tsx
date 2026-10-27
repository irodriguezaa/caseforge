"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import { ExecutivePieChart } from "@/app/components/ExecutivePieChart";
import { ExecutionPriorityBars } from "@/app/components/ExecutionPriorityBars";
import { GroupedStackedBars } from "@/app/components/GroupedStackedBars";
import { api } from "@/lib/api";
import { JiraFilterLink } from "@/app/components/JiraFilterLink";
import { jiraIssueUrl } from "@/lib/jira";
import type { SprintTestingOptions, SprintTestingRead } from "@/lib/types";

function formatJiraDateTime(raw: string | null | undefined): string {
  if (!raw) {
    return "—";
  }
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) {
    return raw;
  }
  return parsed.toLocaleString("es-MX", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function formatStatusChange(row: {
  status_changed_at?: string | null;
  status_changed_from?: string | null;
  status_changed_to?: string | null;
}): string {
  const when = formatJiraDateTime(row.status_changed_at);
  if (when === "—") {
    return "—";
  }
  if (row.status_changed_from && row.status_changed_to) {
    return `${when} · ${row.status_changed_from} → ${row.status_changed_to}`;
  }
  return when;
}

function formatLastComment(row: {
  last_comment_at?: string | null;
  last_comment_author?: string | null;
}): string {
  const when = formatJiraDateTime(row.last_comment_at);
  if (when === "—") {
    return "—";
  }
  if (row.last_comment_author) {
    return `${when} · ${row.last_comment_author}`;
  }
  return when;
}

function JiraKeyLink({ issueKey }: { issueKey: string }): React.ReactElement {
  const href = jiraIssueUrl(issueKey);
  if (!href) {
    return <>{issueKey}</>;
  }
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" title={`Abrir ${issueKey} en Jira`}>
      {issueKey}
    </a>
  );
}

export default function SprintTestingPage(): React.ReactElement {
  const [options, setOptions] = useState<SprintTestingOptions | null>(null);
  const [sprint, setSprint] = useState("44");
  const [swf, setSwf] = useState("hitss");
  const [data, setData] = useState<SprintTestingRead | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exportingIssues, setExportingIssues] = useState(false);
  const [exportingReport, setExportingReport] = useState(false);
  const [exportingPack, setExportingPack] = useState(false);

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
  const packSwfs = options?.pack_swfs ?? [];
  const packAvailable = Boolean(options?.pack_available && packSwfs.length > 0);
  const packLabel = packSwfs.map((item) => item.label).join(" + ");

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

  async function handleExportPack(): Promise<void> {
    setExportingPack(true);
    setError(null);
    try {
      await api.exportSprintTestingPack(sprint);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "No se pudo generar el pack ejecutivo.");
    } finally {
      setExportingPack(false);
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
        {packAvailable && (
          <button
            type="button"
            className="secondary"
            disabled={!canQuery || loading || exportingPack}
            onClick={() => void handleExportPack()}
            title={`PPTX (estado y blockers por SWF) + Excel de blockers (${packLabel})`}
          >
            {exportingPack ? "Generando pack..." : `Pack ${packLabel}`}
          </button>
        )}
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
                Filtro Jira: <JiraFilterLink filterId={data.sprint.filter_id} />
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
            {data.execution.programs.length === 0 ? (
              <p className="muted">No hay issues de ejecución para este SWF.</p>
            ) : (
              <>
                <ExecutionPriorityBars programs={data.execution.programs} />
                <h3 style={{ margin: "18px 0 4px", fontSize: "13px" }}>Blockers</h3>
                <p className="muted" style={{ margin: "0 0 8px", fontSize: "11px" }}>
                  Solo issues abiertos. No se incluyen Done, Roll Out ni Cancelados.
                </p>
                {data.execution.blockers.length === 0 ? (
                  <p className="muted">No hay Blockers para este SWF.</p>
                ) : (
                  <div className="blockers-wrap">
                  <table className="activity blockers">
                    <thead>
                      <tr>
                        <th>Key</th>
                        <th>Summary</th>
                        <th>Issue Type</th>
                        <th>Estado</th>
                        <th>Creación</th>
                        <th>Principal</th>
                        <th>Cambio de estado</th>
                        <th>Último comentario</th>
                        <th>Anidados</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.execution.programs
                        .filter((program) => program.blocker > 0)
                        .map((program) => {
                          const rows = data.execution!.blockers.filter(
                            (row) => row.program_key === program.program_key,
                          );
                          return (
                            <Fragment key={program.program_key}>
                              <tr className="group">
                                <td colSpan={9}>
                                  {program.display_name}{" "}
                                  <span className="muted">({program.blocker})</span>
                                </td>
                              </tr>
                              {rows.map((row) => (
                                  <tr key={`${program.program_key}-${row.key}`}>
                                    <td>
                                      <JiraKeyLink issueKey={row.key} />
                                    </td>
                                    <td>{row.summary}</td>
                                    <td>{row.issue_type || "—"}</td>
                                    <td>{row.status}</td>
                                    <td>{formatJiraDateTime(row.created)}</td>
                                    <td>
                                      {row.principal ? <JiraKeyLink issueKey={row.principal} /> : "—"}
                                    </td>
                                    <td>{formatStatusChange(row)}</td>
                                    <td>{formatLastComment(row)}</td>
                                    <td className="nested">
                                      {row.nested_issue_keys && row.nested_issue_keys.length > 0
                                        ? row.nested_issue_keys.map((nestedKey, index) => (
                                            <Fragment key={nestedKey}>
                                              {index > 0 ? ", " : null}
                                              <JiraKeyLink issueKey={nestedKey} />
                                            </Fragment>
                                          ))
                                        : "—"}
                                    </td>
                                  </tr>
                              ))}
                            </Fragment>
                          );
                        })}
                    </tbody>
                  </table>
                  </div>
                )}
              </>
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
