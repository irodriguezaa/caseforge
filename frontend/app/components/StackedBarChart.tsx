"use client";

import { useState } from "react";
import { MONTHS } from "@/lib/constants";

const PALETTE = ["var(--kpi-blue)", "var(--kpi-teal)", "var(--kpi-gray)"];

function monthLabel(key: string): string {
  // "2026-06" -> "Junio". Falls back to the raw key for non-month keys (e.g. SWF names used as
  // the x-axis in Severidad por SWF).
  const suffix = key.slice(5);
  const match = MONTHS.find((m) => m.value === suffix);
  return match ? match.label : key;
}

export function StackedBarChart({
  data,
  categories,
  colors,
  formatLabel,
  fullHeight = false,
  isMonthly = false,
}: {
  data: Record<string, Record<string, number>>; // "2026-04" -> { BLOCKER: 2, CRITICAL: 5 }
  categories: string[]; // stacking order, also drives the legend
  colors?: Record<string, string>;
  formatLabel?: (key: string) => string;
  // When true, every bar renders at 100% height (pure % composition per key) instead of being
  // scaled by absolute volume -- needed for "Severidad por SWF", where a low-volume SWF must
  // not visually shrink just because another SWF has more total tickets.
  fullHeight?: boolean;
  // When true, keys are treated as "YYYY-MM" and rendered with full Spanish month names, plus
  // a discreet Mundial 2026 marker on June.
  isMonthly?: boolean;
}): React.ReactElement {
  const [hovered, setHovered] = useState<string | null>(null);
  const keys = Object.keys(data).sort();
  const totals = keys.map((k) => categories.reduce((sum, c) => sum + (data[k]?.[c] ?? 0), 0));
  const max = Math.max(1, ...totals);

  const label = (key: string): string => (formatLabel ? formatLabel(key) : isMonthly ? monthLabel(key) : key);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: "8px", height: "150px" }}>
        {keys.map((key, idx) => {
          const isJune = isMonthly && key.endsWith("-06");
          return (
            <div
              key={key}
              style={{ flex: 1, position: "relative", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-end", gap: "6px", height: "100%", cursor: "default" }}
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
                    {label(key)}
                    {isJune && " ⚽ Mundial 2026"}
                  </div>
                  <div style={{ color: "var(--text-muted)" }}>Total: {totals[idx]}</div>
                  {categories.map((cat) => (
                    <div key={cat} style={{ color: colors?.[cat] ?? "var(--text-muted)" }}>
                      {cat}: {data[key]?.[cat] ?? 0}
                    </div>
                  ))}
                  {isJune && <div style={{ color: "var(--text-dim)", marginTop: "4px", fontSize: "10px" }}>Pico de volumen asociado al periodo.</div>}
                </div>
              )}
              <span style={{ fontSize: "10px", color: "var(--text-dim)", fontVariantNumeric: "tabular-nums" }}>{totals[idx] || ""}</span>
              <div style={{ width: "100%", maxWidth: "30px", display: "flex", flexDirection: "column-reverse", height: fullHeight ? "100%" : `${(totals[idx] / max) * 100}%`, minHeight: totals[idx] > 0 ? "2px" : 0, borderRadius: "3px 3px 0 0", overflow: "hidden" }}>
                {categories.map((cat, cIdx) => {
                  const value = data[key]?.[cat] ?? 0;
                  if (!value) return null;
                  const heightPct = (value / (totals[idx] || 1)) * 100;
                  return (
                    <div key={cat} style={{ width: "100%", height: `${heightPct}%`, background: colors?.[cat] ?? PALETTE[cIdx % PALETTE.length] }} />
                  );
                })}
              </div>
              <span style={{ fontSize: "10px", color: "var(--text-dim)" }}>
                {isMonthly ? label(key).slice(0, 3) : label(key)}
                {isJune && " ⚽"}
              </span>
            </div>
          );
        })}
        {keys.length === 0 && <p className="muted">Sin datos todavía.</p>}
      </div>
      {keys.length > 0 && (
        <div style={{ display: "flex", gap: "14px", flexWrap: "wrap", marginTop: "12px" }}>
          {categories.map((cat, idx) => (
            <span key={cat} style={{ display: "inline-flex", alignItems: "center", gap: "5px", fontSize: "11px", color: "var(--text-muted)" }}>
              <span style={{ width: "8px", height: "8px", borderRadius: "2px", background: colors?.[cat] ?? PALETTE[idx % PALETTE.length] }} />
              {cat}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
