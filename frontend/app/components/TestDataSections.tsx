"use client";

import { parseStoredTestData } from "@/lib/parseStoredTestData";

export function TestDataSections({ raw }: { raw: string }): React.ReactElement {
  const parsed = parseStoredTestData(raw);
  if (!parsed) {
    return <></>;
  }

  const { precondition, rows, notes } = parsed;
  const hasStructure = Boolean(precondition || rows.length || notes);
  if (!hasStructure) {
    return (
      <div className="card" style={{ marginTop: "12px" }}>
        <h2>Datos de Prueba</h2>
        <p style={{ whiteSpace: "pre-wrap", margin: 0 }}>{raw}</p>
      </div>
    );
  }

  return (
    <div className="test-data-stack">
      {precondition ? (
        <div className="card">
          <h2>Precondición</h2>
          <p style={{ whiteSpace: "pre-wrap", margin: 0 }}>{precondition}</p>
        </div>
      ) : null}
      {rows.length > 0 ? (
        <div className="card">
          <h2>Datos de prueba</h2>
          <table className="test-data-table">
            <thead>
              <tr>
                <th>Dato</th>
                <th>Valor</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={`${row.label}:${row.value}`}>
                  <td>
                    <code>{row.label}</code>
                  </td>
                  <td>{row.value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {notes ? (
        <details className="card test-data-notes">
          <summary>Notas técnicas</summary>
          <p className="test-data-notes-body">{notes}</p>
        </details>
      ) : null}
    </div>
  );
}
