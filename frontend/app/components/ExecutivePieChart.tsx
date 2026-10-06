"use client";

const OPEN_COLOR = "#3D5A80";
const CLOSED_COLOR = "#2A9D8F";

export function ExecutivePieChart({
  open,
  closed,
}: {
  open: number;
  closed: number;
}): React.ReactElement {
  const total = open + closed;
  const openPct = total ? (open / total) * 100 : 0;
  const closedPct = total ? (closed / total) * 100 : 0;
  const radius = 72;
  const circumference = 2 * Math.PI * radius;
  const closedDash = (closedPct / 100) * circumference;
  const openDash = (openPct / 100) * circumference;

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: "40px",
        flexWrap: "wrap",
        padding: "8px 0 4px",
      }}
    >
      <svg width="200" height="200" viewBox="0 0 200 200" aria-label="Abiertos vs cerrados">
        <circle cx="100" cy="100" r={radius} fill="none" stroke="var(--surface-2)" strokeWidth="28" />
        {total > 0 && (
          <>
            <circle
              cx="100"
              cy="100"
              r={radius}
              fill="none"
              stroke={CLOSED_COLOR}
              strokeWidth="28"
              strokeDasharray={`${closedDash} ${circumference - closedDash}`}
              strokeLinecap="butt"
              transform="rotate(-90 100 100)"
            />
            <circle
              cx="100"
              cy="100"
              r={radius}
              fill="none"
              stroke={OPEN_COLOR}
              strokeWidth="28"
              strokeDasharray={`${openDash} ${circumference - openDash}`}
              strokeDashoffset={-closedDash}
              strokeLinecap="butt"
              transform="rotate(-90 100 100)"
            />
          </>
        )}
        <text x="100" y="96" textAnchor="middle" fill="var(--text)" fontSize="22" fontWeight="700">
          {total}
        </text>
        <text x="100" y="116" textAnchor="middle" fill="var(--text-muted)" fontSize="11">
          Technical Epics
        </text>
      </svg>
      <div style={{ display: "flex", flexDirection: "column", gap: "14px", minWidth: "200px" }}>
        {[
          { label: "Abierto", value: open, pct: openPct, color: OPEN_COLOR },
          { label: "Cerrado", value: closed, pct: closedPct, color: CLOSED_COLOR },
        ].map((row) => (
          <div key={row.label} style={{ display: "flex", alignItems: "baseline", gap: "12px" }}>
            <span style={{ width: "10px", height: "10px", borderRadius: "99px", background: row.color, flexShrink: 0 }} />
            <div>
              <div style={{ fontSize: "13px", color: "var(--text)", fontWeight: 600 }}>{row.label}</div>
              <div style={{ fontSize: "12px", color: "var(--text-muted)", fontVariantNumeric: "tabular-nums" }}>
                {row.value} · {row.pct.toFixed(1)}%
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
