"use client";

import { useCallback, useEffect, useState } from "react";

type CheckStatus = "idle" | "loading" | "ok" | "error";

interface HealthResponse {
  status: string;
  service: string;
  message?: string;
}

interface SystemState {
  backend: CheckStatus;
  database: CheckStatus;
}

const labelForStatus = (status: CheckStatus): string => {
  if (status === "loading") return "Comprobando…";
  if (status === "ok") return "OK";
  if (status === "error") return "Error";
  return "Sin comprobar";
};

const healthCheckTimeoutMs = 5_000;

export default function HomePage(): React.ReactElement {
  const [system, setSystem] = useState<SystemState>({ backend: "idle", database: "idle" });

  const checkConnection = useCallback(async (): Promise<void> => {
    setSystem({ backend: "loading", database: "loading" });

    const check = async (path: string): Promise<CheckStatus> => {
      try {
        const response = await fetch(path, {
          cache: "no-store",
          signal: AbortSignal.timeout(healthCheckTimeoutMs),
        });
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

  return (
    <main>
      <section aria-labelledby="caseforge-title">
        <p className="eyebrow">CaseForge Web v0.1</p>
        <h1 id="caseforge-title">CASEFORGE</h1>
        <p className="subtitle">QC Intelligence Platform</p>

        <div className="status-card" aria-live="polite">
          <h2>Estado del sistema</h2>
          <dl>
            <div><dt>Frontend</dt><dd className="ok">OK</dd></div>
            <div><dt>Backend</dt><dd className={system.backend}>{labelForStatus(system.backend)}</dd></div>
            <div><dt>Database</dt><dd className={system.database}>{labelForStatus(system.database)}</dd></div>
          </dl>
        </div>

        <button type="button" onClick={checkConnection} disabled={system.backend === "loading"}>
          {system.backend === "loading" ? "Comprobando conexión…" : "Comprobar conexión"}
        </button>
      </section>
    </main>
  );
}
