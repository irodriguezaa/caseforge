"use client";

import { useState } from "react";
import type { SprintTestingProgramMetrics } from "@/lib/types";

const BAR_KEYS = [
  { id: "development", label: "Desarrollo" },
  { id: "testing", label: "Testing" },
  { id: "closed", label: "Cerrado" },
] as const;

/** Dark-theme executive palette: sand / steel / sage (high contrast, low saturation). */
const DEV_COLOR = "#C4B59A";
const CLOSED_COLOR = "#4A9B82";
const TESTING_COLORS: Record<string, string> = {
  Integration: "#7B6D8D",
  "QA Validation": "#4C7D9E",
  "QC Validation": "#7D8794",
  Validation: "#7D8794",
};
const TESTING_LEGEND = [
  { label: "QA Validation", color: "#4C7D9E" },
  { label: "Validation", color: "#7D8794" },
  { label: "Integration", color: "#7B6D8D" },
];

function barTotal(counts: Record<string, number>): number {
  return Object.values(counts).reduce((sum, value) => sum + value, 0);
}

function segmentColor(barId: string, status: string): string {
  if (barId === "development") return DEV_COLOR;
  if (barId === "closed") return CLOSED_COLOR;
  return TESTING_COLORS[status] ?? "#7D8794";
}

export function GroupedStackedBars({
  programs,
}: {
  programs: SprintTestingProgramMetrics[];
}): React.ReactElement {
  const [hovered, setHovered] = useState<string | null>(null);
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
      <div
        style={{
          display: "flex",
          alignItems: "stretch",
          width: "100%",
          minHeight: "220px",
        }}
      >
        {programs.map((program, index) => (
          <div
            key={program.program_key}
            style={{
              flex: "1 1 0",
              minWidth: 0,
              padding: "0 14px",
              borderLeft: index === 0 ? "none" : "1px solid var(--border-strong)",
            }}
          >
            <div style={{ display: "flex", alignItems: "flex-end", gap: "6px", height: "180px" }}>
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
                          <div key={status} style={{ color: "var(--text)" }}>
                            {status}: {value}
                          </div>
                        ))}
                      </div>
                    )}
                    <span style={{ fontSize: "11px", color: "var(--text-muted)", fontVariantNumeric: "tabular-nums" }}>
                      {total || ""}
                    </span>
                    <div
                      style={{
                        width: "100%",
                        maxWidth: "48px",
                        display: "flex",
                        flexDirection: "column-reverse",
                        height: `${(total / maxBar) * 100}%`,
                        minHeight: total > 0 ? "2px" : 0,
                        borderRadius: "4px 4px 0 0",
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
                              background: segmentColor(bar.id, status),
                            }}
                          />
                        );
                      })}
                    </div>
                    <span style={{ fontSize: "10px", color: "var(--text-dim)", textAlign: "center", lineHeight: 1.2 }}>
                      {bar.label}
                    </span>
                  </div>
                );
              })}
            </div>
            <div
              style={{
                marginTop: "10px",
                fontSize: "12px",
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
      <div style={{ display: "flex", gap: "16px", flexWrap: "wrap", marginTop: "16px" }}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: "5px", fontSize: "11px", color: "var(--text-muted)" }}>
          <span style={{ width: "8px", height: "8px", borderRadius: "2px", background: DEV_COLOR }} />
          Desarrollo
        </span>
        {TESTING_LEGEND.map((item) => (
          <span
            key={item.label}
            style={{ display: "inline-flex", alignItems: "center", gap: "5px", fontSize: "11px", color: "var(--text-muted)" }}
          >
            <span style={{ width: "8px", height: "8px", borderRadius: "2px", background: item.color }} />
            {item.label}
          </span>
        ))}
        <span style={{ display: "inline-flex", alignItems: "center", gap: "5px", fontSize: "11px", color: "var(--text-muted)" }}>
          <span style={{ width: "8px", height: "8px", borderRadius: "2px", background: CLOSED_COLOR }} />
          Cerrado
        </span>
      </div>
    </div>
  );
}
