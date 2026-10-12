"use client";

import { useEffect, useMemo, useState } from "react";
import { api, ApiRequestError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { QcMatrixDetail, QcMatrixSummary } from "@/lib/types";

const SCREEN_ORDER = ["Pantallas grandes", "Pantallas medianas", "Pantallas chicas"];

function screenRank(screen: string): number {
  const index = SCREEN_ORDER.indexOf(screen);
  return index === -1 ? SCREEN_ORDER.length + 1 : index;
}

export default function MatricesPage(): React.ReactElement {
  const { canChangeReleaseStatus } = useAuth();
  const [rows, setRows] = useState<QcMatrixSummary[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<QcMatrixDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [moduleFilter, setModuleFilter] = useState("");
  const [smokeFilter, setSmokeFilter] = useState("");
  const [severityFilter, setSeverityFilter] = useState("");
  const [regionFilter, setRegionFilter] = useState("");
  const [deviceFilter, setDeviceFilter] = useState("");

  const loadList = (): void => {
    api
      .listQcMatrices()
      .then((data) => {
        setRows(data);
        setSelectedId((current) => current ?? data[0]?.id ?? null);
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiRequestError ? err.message : "No se pudieron cargar las matrices.");
      });
  };

  useEffect(() => {
    loadList();
  }, []);

  useEffect(() => {
    if (selectedId == null) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    api
      .getQcMatrix(selectedId)
      .then((data) => {
        if (!cancelled) setDetail(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof ApiRequestError ? err.message : "No se pudo abrir la matriz.");
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  const devices = useMemo(() => {
    const list = [...(detail?.devices ?? [])];
    list.sort((a, b) => screenRank(a.screen) - screenRank(b.screen) || a.code.localeCompare(b.code));
    return list;
  }, [detail]);

  const screenGroups = useMemo(() => {
    const groups: { screen: string; devices: typeof devices }[] = [];
    for (const device of devices) {
      const screen = device.screen || "Sin tamaño";
      const last = groups[groups.length - 1];
      if (!last || last.screen !== screen) groups.push({ screen, devices: [device] });
      else last.devices.push(device);
    }
    return groups;
  }, [devices]);

  const visibleCases = useMemo(() => {
    return (detail?.cases ?? []).filter((row) => {
      if (moduleFilter && row.module_key !== moduleFilter) return false;
      if (smokeFilter === "yes" && !row.smoke) return false;
      if (smokeFilter === "no" && row.smoke) return false;
      if (severityFilter && row.severity !== severityFilter) return false;
      if (regionFilter && (row.region || "Sin región") !== regionFilter) return false;
      if (deviceFilter && !row.platforms.includes(deviceFilter)) return false;
      return true;
    });
  }, [detail, moduleFilter, smokeFilter, severityFilter, regionFilter, deviceFilter]);

  const onImport = async (file: File | undefined): Promise<void> => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const created = await api.importQcMatrix(file);
      setSelectedId(created.id);
      loadList();
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "No se pudo importar la matriz.");
    } finally {
      setBusy(false);
    }
  };

  const onPublish = async (): Promise<void> => {
    if (!detail) return;
    setBusy(true);
    setError(null);
    try {
      await api.publishQcMatrix(detail.id);
      loadList();
      setDetail(await api.getQcMatrix(detail.id));
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "No se pudo publicar la versión.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <div className="section-header">
        <h1>Matrices QC</h1>
        {canChangeReleaseStatus && (
          <label className="button">
            {busy ? "Importando…" : "Importar JSON o Excel"}
            <input
              type="file"
              accept=".json,.xlsx,application/json"
              hidden
              disabled={busy}
              onChange={(event) => {
                const file = event.target.files?.[0];
                event.target.value = "";
                void onImport(file);
              }}
            />
          </label>
        )}
      </div>
      <p className="muted">
        Solo una versión publicada por matriz. Republicar una versión anterior la deja vigente y pasa la actual a histórico, sin borrar ninguna.
      </p>
      {error && <p className="error-text">{error}</p>}

      <table>
        <thead>
          <tr>
            <th>Matriz</th>
            <th>Versión</th>
            <th>Estado</th>
            <th>Módulos</th>
            <th>Dispositivos</th>
            <th>Casos</th>
            <th>Publicó</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.id}
              className={row.id === selectedId ? "selected" : "clickable"}
              onClick={() => setSelectedId(row.id)}
            >
              <td>{row.name}</td>
              <td>{row.version}</td>
              <td>{row.status}</td>
              <td>{row.module_count}</td>
              <td>{row.device_count}</td>
              <td>{row.case_count}</td>
              <td>{row.published_by ? `${row.published_by}` : "—"}</td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={7} className="muted">Sin matrices importadas.</td>
            </tr>
          )}
        </tbody>
      </table>

      {detail && (
        <div style={{ marginTop: "1.25rem" }}>
          <div className="section-header">
            <h2>
              {detail.code} {detail.version} · {detail.status}
            </h2>
            <div className="form-actions">
              {canChangeReleaseStatus && detail.status !== "published" && (
                <button type="button" disabled={busy} onClick={() => void onPublish()}>
                  {detail.status === "historical" ? "Republicar" : "Publicar"}
                </button>
              )}
              <a className="button" href={`/api/qc-matrices/${detail.id}/export`}>
                Exportar Excel
              </a>
            </div>
          </div>
          <div className="filter-bar">
            <select value={moduleFilter} onChange={(event) => setModuleFilter(event.target.value)}>
              <option value="">Módulo</option>
              {detail.modules.map((module) => (
                <option key={module.module_key} value={module.module_key}>
                  {module.module_key} · {module.name}
                </option>
              ))}
            </select>
            <select value={smokeFilter} onChange={(event) => setSmokeFilter(event.target.value)}>
              <option value="">Smoke</option>
              <option value="yes">Smoke</option>
              <option value="no">No smoke</option>
            </select>
            <select value={severityFilter} onChange={(event) => setSeverityFilter(event.target.value)}>
              <option value="">Severidad</option>
              <option value="Blocker">Blocker</option>
              <option value="Critical">Critical</option>
            </select>
            <select value={regionFilter} onChange={(event) => setRegionFilter(event.target.value)}>
              <option value="">Región</option>
              {[...new Set(detail.cases.map((row) => row.region || "Sin región"))].map((region) => (
                <option key={region} value={region}>
                  {region}
                </option>
              ))}
            </select>
            <select value={deviceFilter} onChange={(event) => setDeviceFilter(event.target.value)}>
              <option value="">Dispositivo</option>
              {devices.map((device) => (
                <option key={device.code} value={device.code}>
                  {device.label}
                </option>
              ))}
            </select>
            <span className="muted">{visibleCases.length} casos</span>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table className="case-grid">
              <thead>
                <tr>
                  <th rowSpan={2}>ID</th>
                  <th rowSpan={2}>Módulo</th>
                  <th rowSpan={2}>Título</th>
                  <th rowSpan={2}>Severidad</th>
                  <th rowSpan={2}>Smoke</th>
                  <th rowSpan={2}>Región</th>
                  {screenGroups.map((group) => (
                    <th key={group.screen} colSpan={group.devices.length}>
                      {group.screen}
                    </th>
                  ))}
                </tr>
                <tr>
                  {devices.map((device) => (
                    <th key={device.code} title={device.label}>
                      {device.code}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visibleCases.map((row) => (
                  <tr key={row.id} title={`${row.steps}\n\n${row.expected}`}>
                    <td>{row.base_id || "—"}</td>
                    <td>{row.module_key || "—"}</td>
                    <td>{row.title}</td>
                    <td>{row.severity}</td>
                    <td>{row.smoke ? "Sí" : "—"}</td>
                    <td>{row.region || "—"}</td>
                    {devices.map((device) => (
                      <td key={device.code} title={row.platform_notes[device.code] || undefined}>
                        {row.platforms.includes(device.code) ? "✔" : ""}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
