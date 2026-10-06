"use client";

import { useState } from "react";
import type { SprintTestingProgramMetrics } from "@/lib/types";

const BAR_KEYS = [
  { id: "development", label: "Desarrollo" },
  { id: "testing", label: "Testing" },
  { id: "closed", label: "Cerrado" },
] as const;

const PALETTE = [
  "var(--kpi-blue)",
  "var(--kpi-teal)",
  "var(--warning)",
  "var(--kpi-gray)",
  "var(--success)",
  "var(--danger)",
  "var(--accent)",
  "#8b7ec8",
  "#c47a54",
  "#5aa2a0",
];

function barTotal(counts: Record<string, number>): number {
  return Object.values(counts).reduce((sum, value) => sum + value, 0);
}

export function GroupedStackedBars({
  programs,
}: {
  programs: SprintTestingProgramMetrics[];
}): React.ReactElement {
  const [hovered, setHovered] = useState<string | null>(null);
  const statuses = Array.from(
    new Set(
      programs.flatMap((row) => [
        ...Object.keys(row.development),
        ...Object.keys(row.testing),
        ...Object.keys(row.closed),
      ]),
    ),
  );
  const colorOf = (status: string): string => PALETTE[statuses.indexOf(status) % PALETTE.length];
  const maxBar = Math.max(
    1,
    ...programs.flatMap((row) => [
      barTotal(row.development),
      barTotal(row.testing),
      barTotal(row.closed),
    ]),
  );

  return (
    <div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: "28px", overflowX: "auto", minHeight: "190px" }}>
        {programs.map((program) => (
          <div key={program.program_key} style={{ minWidth: "132px", flex: "0 0 auto" }}>
            <div style={{ display: "flex", alignItems: "flex-end", gap: "8px", height: "160px" }}>
              {BAR_KEYS.map((bar) => {
                const counts = program[bar.id];
                const total = barTotal(counts);
                const hoverKey = `${program.program_key}:${bar.id}`;
                return (
                  <div
                    key={bar.id}
                    style={{
                      flex: 1,
                      position: "relative",
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "center",
                      justifyContent: "flex-end",
                      gap: "6px",
                      height: "100%",
                    }}
                    onMouseEnter={() => setHovered(hoverKey)}
                    onMouseLeave={() => setHovered((current) => (current === hoverKey ? null : current))}
                  >
                    {hovered === hoverKey && (
                      <div
                        style={{
                          position: "absolute",
                          bottom: "100%",
                          left: "50%",
                          transform: "translateX(-50%)",
                          marginBottom: "6px",
                          background: "var(--surface-2)",
                          border: "1px solid var(--border)",
                          borderRadius: "8px",
                          padding: "8px 10px",
                          fontSize: "11px",
                          whiteSpace: "nowrap",
                          zIndex: 15,
                        }}
                      >
                        <div style={{ fontWeight: 700, marginBottom: "4px" }}>
                          {program.display_name} · {bar.label}
                        </div>
                        <div style={{ color: "var(--text-muted)" }}>Total: {total}</div>
                        {Object.entries(counts).map(([status, value]) => (
                          <div key={status} style={{ color: colorOf(status) }}>
                            {status}: {value}
                          </div>
                        ))}
                      </div>
                    )}
                    <span style={{ fontSize: "10px", color: "var(--text-dim)", fontVariantNumeric: "tabular-nums" }}>
                      {total || ""}
                    </span>
                    <div
                      style={{
                        width: "100%",
                        maxWidth: "28px",
                        display: "flex",
                        flexDirection: "column-reverse",
                        height: `${(total / maxBar) * 100}%`,
                        minHeight: total > 0 ? "2px" : 0,
                        borderRadius: "3px 3px 0 0",
                        overflow: "hidden",
                        background: total === 0 ? "var(--surface-2)" : undefined,
                      }}
                    >
                      {Object.entries(counts).map(([status, value]) => {
                        if (!value) return null;
                        return (
                          <div
                            key={status}
                            style={{
                              width: "100%",
                              height: `${(value / (total || 1)) * 100}%`,
                              background: colorOf(status),
                            }}
                          />
                        );
                      })}
                    </div>
                    <span style={{ fontSize: "9px", color: "var(--text-dim)", textAlign: "center" }}>{bar.label}</span>
                  </div>
                );
              })}
            </div>
            <div
              style={{
                marginTop: "8px",
                fontSize: "11px",
                color: "var(--text)",
                textAlign: "center",
                fontWeight: 600,
              }}
            >
              {program.display_name}
            </div>
          </div>
        ))}
      </div>
      {statuses.length > 0 && (
        <div style={{ display: "flex", gap: "14px", flexWrap: "wrap", marginTop: "14px" }}>
          {statuses.map((status) => (
            <span
              key={status}
              style={{ display: "inline-flex", alignItems: "center", gap: "5px", fontSize: "11px", color: "var(--text-muted)" }}
            >
              <span style={{ width: "8px", height: "8px", borderRadius: "2px", background: colorOf(status) }} />
              {status}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
