"use client";

import { useState } from "react";
import type { TestCaseStatus } from "@/lib/types";

const STATUSES: TestCaseStatus[] = ["UNEXECUTED", "PASS", "FAIL", "BLOCKED", "N_A"];

interface TestCaseBulkBarProps {
  count: number;
  busy: boolean;
  onClear: () => void;
  onChangeStatus: (status: TestCaseStatus) => Promise<void>;
  onDelete: () => Promise<void>;
}

export function TestCaseBulkBar({
  count,
  busy,
  onClear,
  onChangeStatus,
  onDelete,
}: TestCaseBulkBarProps): React.ReactElement {
  const [statusOpen, setStatusOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [status, setStatus] = useState<TestCaseStatus>("PASS");

  const closeDialogs = (): void => {
    if (busy) return;
    setStatusOpen(false);
    setDeleteOpen(false);
  };

  return (
    <>
      <div className="bulk-bar" role="region" aria-label="Acciones masivas de casos de prueba">
        <strong>
          {count} caso{count === 1 ? "" : "s"} seleccionado{count === 1 ? "" : "s"}
        </strong>
        <span className="muted" style={{ fontSize: "12px" }}>
          Resultados filtrados de esta Release
        </span>
        <div className="form-actions" style={{ margin: 0, marginLeft: "auto" }}>
          <button type="button" disabled={busy || count === 0} onClick={() => setStatusOpen(true)}>
            Cambiar estado
          </button>
          <button
            type="button"
            className="danger"
            disabled={busy || count === 0}
            onClick={() => setDeleteOpen(true)}
          >
            Eliminar seleccionados
          </button>
          <button type="button" className="secondary" disabled={busy} onClick={onClear}>
            Limpiar selección
          </button>
        </div>
      </div>

      {statusOpen ? (
        <div className="modal-backdrop" onClick={closeDialogs} role="presentation">
          <div
            className="modal-panel"
            role="dialog"
            aria-labelledby="bulk-status-title"
            onClick={(event) => event.stopPropagation()}
            style={{ width: "min(420px, 100%)" }}
          >
            <h2 id="bulk-status-title">Cambiar estado</h2>
            <p className="muted">
              Se actualizará el estado de {count} caso{count === 1 ? "" : "s"} seleccionado
              {count === 1 ? "" : "s"}. No se modificarán otros campos ni casos fuera de la
              selección.
            </p>
            <div className="form-field">
              <label htmlFor="bulk-status">Estado destino</label>
              <select
                id="bulk-status"
                value={status}
                onChange={(event) => setStatus(event.target.value as TestCaseStatus)}
                disabled={busy}
              >
                {STATUSES.map((value) => (
                  <option key={value} value={value}>
                    {value === "N_A" ? "N/A" : value}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-actions">
              <button type="button" className="secondary" disabled={busy} onClick={closeDialogs}>
                Cancelar
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => {
                  void onChangeStatus(status).then(() => setStatusOpen(false));
                }}
              >
                {busy ? "Guardando…" : `Aplicar a ${count} caso${count === 1 ? "" : "s"}`}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {deleteOpen ? (
        <div className="modal-backdrop" onClick={closeDialogs} role="presentation">
          <div
            className="modal-panel"
            role="dialog"
            aria-labelledby="bulk-delete-title"
            onClick={(event) => event.stopPropagation()}
            style={{ width: "min(460px, 100%)" }}
          >
            <h2 id="bulk-delete-title">¿Eliminar {count} casos de prueba?</h2>
            <p>
              Esta acción eliminará los {count} casos seleccionados de la Release. No se
              eliminarán casos de otras Epics ni casos fuera de la selección.
            </p>
            <div className="form-actions">
              <button type="button" className="secondary" disabled={busy} onClick={closeDialogs}>
                Cancelar
              </button>
              <button
                type="button"
                className="danger"
                disabled={busy}
                onClick={() => {
                  void onDelete().then(() => setDeleteOpen(false));
                }}
              >
                {busy ? "Eliminando…" : "Confirmar eliminación"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
