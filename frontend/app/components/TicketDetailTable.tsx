"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { QcTicketRead, QcTicketView } from "@/lib/types";

const PAGE_SIZE = 20;

export function TicketDetailTable({ view }: { view: QcTicketView }): React.ReactElement {
  const [tickets, setTickets] = useState<QcTicketRead[]>([]);
  const [page, setPage] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setPage(0);
    api.listQcTickets(view).then(setTickets).catch((err: unknown) => setError(err instanceof Error ? err.message : "Error"));
  }, [view]);

  if (error) return <p className="error-text">{error}</p>;
  if (tickets.length === 0) return <p className="muted">Sin tickets cargados todavía.</p>;

  const totalPages = Math.ceil(tickets.length / PAGE_SIZE);
  const pageRows = tickets.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  return (
    <div>
      <table className="activity">
        <thead>
          <tr>
            <th>Clave</th>
            <th>Prioridad</th>
            <th>Estado</th>
            <th>{view === "OPERATIVAS" ? "Programa" : "Proyecto"}</th>
            <th>SWF</th>
            <th>Origen</th>
            <th>Creada</th>
          </tr>
        </thead>
        <tbody>
          {pageRows.map((t) => (
            <tr key={t.id}>
              <td style={{ fontWeight: 500 }}>{t.issue_key}</td>
              <td>{t.priority_bucket}</td>
              <td className="muted">{t.status_raw}</td>
              <td className="muted">{view === "OPERATIVAS" ? (t.affected_program ?? "—") : (t.project_key ?? "—")}</td>
              <td className="muted">{t.swf ?? "—"}</td>
              <td className="muted">{t.source === "QC_DETECTED" ? "Detección" : "Fuga"}</td>
              <td className="muted">{t.created_date}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {totalPages > 1 && (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 14px", fontSize: "12px", color: "var(--text-dim)" }}>
          <span>
            {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, tickets.length)} de {tickets.length}
          </span>
          <div style={{ display: "flex", gap: "8px" }}>
            <button type="button" className="secondary" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
              Anterior
            </button>
            <button type="button" className="secondary" disabled={page >= totalPages - 1} onClick={() => setPage((p) => p + 1)}>
              Siguiente
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
