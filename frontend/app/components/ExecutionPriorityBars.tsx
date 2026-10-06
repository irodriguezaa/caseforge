"use client";

import type { SprintTestingExecutionProgram } from "@/lib/types";

const BLOCKER_COLOR = "#C45C5C";
const OTHER_COLOR = "#4C6A8A";

export function ExecutionPriorityBars({
  programs,
}: {
  programs: SprintTestingExecutionProgram[];
}): React.ReactElement {
  const max = Math.max(1, ...programs.map((row) => row.total));
  return (
    <div>
      <div style={{ display: "flex", alignItems: "stretch", width: "100%", minHeight: "180px" }}>
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
            <div style={{ display: "flex", alignItems: "flex-end", gap: "8px", height: "140px" }}>
              {[
                { label: "Blocker", value: program.blocker, color: BLOCKER_COLOR },
                { label: "No Blocker", value: program.non_blocker, color: OTHER_COLOR },
              ].map((bar) => (
                <div
                  key={bar.label}
                  style={{
                    flex: 1,
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    justifyContent: "flex-end",
                    gap: "6px",
                    height: "100%",
                  }}
                >
                  <span style={{ fontSize: "11px", color: "var(--text-muted)", fontVariantNumeric: "tabular-nums" }}>
                    {bar.value || ""}
                  </span>
                  <div
                    style={{
                      width: "100%",
                      maxWidth: "42px",
                      height: `${(bar.value / max) * 100}%`,
                      minHeight: bar.value > 0 ? "2px" : 0,
                      borderRadius: "4px 4px 0 0",
                      background: bar.value > 0 ? bar.color : "var(--surface-2)",
                    }}
                  />
                  <span style={{ fontSize: "10px", color: "var(--text-dim)", textAlign: "center" }}>{bar.label}</span>
                </div>
              ))}
            </div>
            <div style={{ marginTop: "10px", fontSize: "12px", fontWeight: 600, textAlign: "center" }}>
              {program.display_name}
            </div>
            <div
              style={{
                marginTop: "2px",
                fontSize: "10px",
                color: "var(--text-muted)",
                textAlign: "center",
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {program.total} issues
            </div>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: "16px", flexWrap: "wrap", marginTop: "16px" }}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: "5px", fontSize: "11px", color: "var(--text-muted)" }}>
          <span style={{ width: "8px", height: "8px", borderRadius: "2px", background: BLOCKER_COLOR }} />
          Blocker
        </span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: "5px", fontSize: "11px", color: "var(--text-muted)" }}>
          <span style={{ width: "8px", height: "8px", borderRadius: "2px", background: OTHER_COLOR }} />
          No Blocker
        </span>
      </div>
    </div>
  );
}
