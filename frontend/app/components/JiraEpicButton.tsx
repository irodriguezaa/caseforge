"use client";

import { useState } from "react";
import { api, ApiRequestError } from "@/lib/api";
import { ACTIVITY_TYPE_OPTIONS, ENVIRONMENT_OPTIONS } from "@/lib/constants";
import { jiraIssueUrl } from "@/lib/jira";

type ActivityType = (typeof ACTIVITY_TYPE_OPTIONS)[number];
type EnvironmentName = (typeof ENVIRONMENT_OPTIONS)[number];

export function JiraEpicButton({
  releaseId,
  activityType,
  environment,
  onSaved,
}: {
  releaseId: number;
  activityType: string | null | undefined;
  environment: string | null | undefined;
  onSaved: (activityType: ActivityType, environment: EnvironmentName) => void;
}): React.ReactElement {
  const [kind, setKind] = useState(activityType ?? "");
  const [env, setEnv] = useState(environment ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ key: string; summary: string; alreadyExisted: boolean } | null>(null);

  async function create(): Promise<void> {
    if (!kind || !env || busy) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created = await api.createJiraEpic(releaseId, {
        activity_type: kind as ActivityType,
        environment: env as EnvironmentName,
      });
      onSaved(kind as ActivityType, env as EnvironmentName);
      setResult({
        key: created.key,
        summary: created.summary,
        alreadyExisted: created.already_existed,
      });
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "No se pudo crear la EPC en Jira.");
    } finally {
      setBusy(false);
    }
  }

  const href = result ? jiraIssueUrl(result.key) : null;

  return (
    <div className="card" style={{ marginTop: "1rem" }}>
      <h2>Artefactos de Jira</h2>
      <p className="muted" style={{ fontSize: "12.5px", marginTop: 0 }}>
        Con los casos ya generados se crea la EPC en QCO. La tarea y las subtareas quedan para el siguiente paso.
      </p>
      <div className="form-actions" style={{ alignItems: "center" }}>
        <label htmlFor="jira-epic-type" className="muted" style={{ margin: 0 }}>Tipo</label>
        <select id="jira-epic-type" value={kind} disabled={busy} onChange={(event) => setKind(event.target.value)}>
          <option value="" disabled>Tipo</option>
          {ACTIVITY_TYPE_OPTIONS.map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
        <label htmlFor="jira-epic-env" className="muted" style={{ margin: 0 }}>Ambiente</label>
        <select id="jira-epic-env" value={env} disabled={busy} onChange={(event) => setEnv(event.target.value)}>
          <option value="" disabled>Ambiente</option>
          {ENVIRONMENT_OPTIONS.map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
        <button type="button" disabled={!kind || !env || busy} onClick={() => void create()}>
          {busy ? "Creando EPC…" : "Generar artefactos de Jira"}
        </button>
      </div>
      {error ? <p className="error-text">{error}</p> : null}
      {result ? (
        <p style={{ fontSize: "13px", marginBottom: 0 }}>
          {result.alreadyExisted ? "Esa EPC ya estaba en Jira." : "EPC creada."}{" "}
          {href ? (
            <a href={href} target="_blank" rel="noreferrer">{result.key}</a>
          ) : (
            result.key
          )}{" "}
          <span className="muted">{result.summary}</span>
        </p>
      ) : null}
    </div>
  );
}
