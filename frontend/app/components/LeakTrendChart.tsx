"use client";

import { useState } from "react";
import { MONTHS } from "@/lib/constants";

function monthLabel(key: string): string {
  const suffix = key.slice(5);
  const match = MONTHS.find((m) => m.value === suffix);
  return match ? match.label : key;
}

export function LeakTrendChart({
  data,
}: {
  data: Record<string, { leaked: number; rate: number }>;
}): React.ReactElement {
  const [hovered, setHovered] = useState<string | null>(null);
  const keys = Object.keys(data).sort();
  const max = Math.max(1, ...keys.map((k) => data[k].leaked));

  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: "8px", height: "150px" }}>
      {keys.map((key) => {
        const isJune = key.endsWith("-06");
        return (
          <div
            key={key}
            style={{ flex: 1, position: "relative", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-end", gap: "6px", height: "100%" }}
            onMouseEnter={() => setHovered(key)}
            onMouseLeave={() => setHovered((h) => (h === key ? null : h))}
          >
            {hovered === key && (
              <div
                style={{
                  position: "absolute", bottom: "100%", left: "50%", transform: "translateX(-50%)", marginBottom: "6px",
                  background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px",
                  padding: "8px 10px", fontSize: "11px", whiteSpace: "nowrap", zIndex: 15, boxShadow: "0 4px 16px rgba(0,0,0,.35)",
                }}
              >
                <div style={{ fontWeight: 700, marginBottom: "4px" }}>
                  {monthLabel(key)}
                  {isJune && " ⚽ Mundial 2026"}
                </div>
                <div style={{ color: "var(--kpi-gold)" }}>Fuga: {data[key].leaked}</div>
                <div style={{ color: "var(--text-muted)" }}>Tasa: {data[key].rate}%</div>
              </div>
            )}
            <span style={{ fontSize: "10px", color: "var(--text-dim)", fontVariantNumeric: "tabular-nums" }}>{data[key].leaked}</span>
            <div style={{ width: "100%", maxWidth: "30px", height: `${(data[key].leaked / max) * 100}%`, minHeight: data[key].leaked > 0 ? "2px" : 0, borderRadius: "3px 3px 0 0", background: "var(--kpi-gold)" }} />
            <span style={{ fontSize: "10px", color: "var(--text-dim)" }}>
              {monthLabel(key).slice(0, 3)}
              {isJune && " ⚽"}
            </span>
            <span style={{ fontSize: "9.5px", color: "var(--kpi-gold)", fontWeight: 600 }}>{data[key].rate}%</span>
          </div>
        );
      })}
      {keys.length === 0 && <p className="muted">Sin datos todavía.</p>}
    </div>
  );
}
