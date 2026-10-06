"use client";

import type { SprintTestingProgramMetrics } from "@/lib/types";

const OPEN_COLOR = "#4C6A8A";
const CLOSED_COLOR = "#4A9B82";

function Donut({
  open,
  closed,
  size,
  title,
  subtitle,
}: {
  open: number;
  closed: number;
  size: "lg" | "sm";
  title: string;
  subtitle?: string;
}): React.ReactElement {
  const total = open + closed;
  const openPct = total ? (open / total) * 100 : 0;
  const closedPct = total ? (closed / total) * 100 : 0;
  const box = size === "lg" ? 168 : 112;
  const radius = size === "lg" ? 58 : 38;
  const stroke = size === "lg" ? 22 : 16;
  const circumference = 2 * Math.PI * radius;
  const closedDash = (closedPct / 100) * circumference;
  const openDash = (openPct / 100) * circumference;
  const cx = box / 2;

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", minWidth: size === "lg" ? 168 : 108 }}>
      <svg width={box} height={box} viewBox={`0 0 ${box} ${box}`} aria-label={title}>
        <circle cx={cx} cy={cx} r={radius} fill="none" stroke="var(--surface-2)" strokeWidth={stroke} />
        {total > 0 && (
          <>
            <circle
              cx={cx}
              cy={cx}
              r={radius}
              fill="none"
              stroke={CLOSED_COLOR}
              strokeWidth={stroke}
              strokeDasharray={`${closedDash} ${circumference - closedDash}`}
              transform={`rotate(-90 ${cx} ${cx})`}
            />
            <circle
              cx={cx}
              cy={cx}
              r={radius}
              fill="none"
              stroke={OPEN_COLOR}
              strokeWidth={stroke}
              strokeDasharray={`${openDash} ${circumference - openDash}`}
              strokeDashoffset={-closedDash}
              transform={`rotate(-90 ${cx} ${cx})`}
            />
          </>
        )}
        <text x={cx} y={cx - 2} textAnchor="middle" fill="var(--text)" fontSize={size === "lg" ? 20 : 14} fontWeight="700">
          {total}
        </text>
        {size === "lg" && (
          <text x={cx} y={cx + 16} textAnchor="middle" fill="var(--text-muted)" fontSize="10">
            Total
          </text>
        )}
      </svg>
      <div style={{ marginTop: "6px", textAlign: "center" }}>
        <div style={{ fontSize: size === "lg" ? 13 : 11, fontWeight: 600, color: "var(--text)", lineHeight: 1.25 }}>
          {title}
        </div>
        {subtitle ? (
          <div style={{ fontSize: 10, color: "var(--text-dim)", marginTop: 2 }}>{subtitle}</div>
        ) : (
          <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 3, fontVariantNumeric: "tabular-nums" }}>
            {open} ({openPct.toFixed(0)}%) · {closed} ({closedPct.toFixed(0)}%)
          </div>
        )}
      </div>
    </div>
  );
}

function ExecutiveArrow(): React.ReactElement {
  return (
    <svg width="44" height="18" viewBox="0 0 44 18" aria-hidden="true" style={{ flexShrink: 0, color: "var(--text-dim)" }}>
      <line x1="2" y1="9" x2="34" y2="9" stroke="currentColor" strokeWidth="1" />
      <polyline points="28,3 36,9 28,15" fill="none" stroke="currentColor" strokeWidth="1" />
    </svg>
  );
}

export function ExecutivePieChart({
  open,
  closed,
  programs,
}: {
  open: number;
  closed: number;
  programs: SprintTestingProgramMetrics[];
}): React.ReactElement {
  const total = open + closed;
  const openPct = total ? (open / total) * 100 : 0;
  const closedPct = total ? (closed / total) * 100 : 0;

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          flexWrap: "wrap",
          justifyContent: "flex-start",
        }}
      >
        <Donut
          size="lg"
          title="Total"
          subtitle={`${open} abiertos · ${closed} cerrados`}
          open={open}
          closed={closed}
        />
        <ExecutiveArrow />
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            gap: "18px",
            flex: 1,
            flexWrap: "wrap",
            justifyContent: "space-evenly",
            minWidth: "240px",
          }}
        >
          {programs.map((program) => (
            <Donut
              key={program.program_key}
              size="sm"
              title={program.display_name}
              open={program.open}
              closed={program.closed_total}
            />
          ))}
        </div>
      </div>
      <div style={{ display: "flex", gap: "18px", flexWrap: "wrap", marginTop: "16px" }}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: "6px", fontSize: "11px", color: "var(--text-muted)" }}>
          <span style={{ width: "8px", height: "8px", borderRadius: "99px", background: OPEN_COLOR }} />
          Abierto {open} · {openPct.toFixed(1)}%
        </span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: "6px", fontSize: "11px", color: "var(--text-muted)" }}>
          <span style={{ width: "8px", height: "8px", borderRadius: "99px", background: CLOSED_COLOR }} />
          Cerrado {closed} · {closedPct.toFixed(1)}%
        </span>
      </div>
    </div>
  );
}
