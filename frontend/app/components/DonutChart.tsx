"use client";

const PALETTE = ["var(--kpi-blue)", "var(--kpi-teal)", "var(--kpi-gray)"];

export function DonutChart({
  items,
  colors,
}: {
  items: { label: string; value: number }[];
  colors?: Record<string, string>;
}): React.ReactElement {
  const total = items.reduce((sum, i) => sum + i.value, 0);
  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  let offsetAcc = 0;

  return (
    <div style={{ display: "flex", alignItems: "center", gap: "20px", flexWrap: "wrap" }}>
      <svg width="110" height="110" viewBox="0 0 110 110" style={{ transform: "rotate(-90deg)", flexShrink: 0 }}>
        <circle cx="55" cy="55" r={radius} fill="none" stroke="var(--border)" strokeWidth="14" />
        {total > 0 &&
          items.map((item, idx) => {
            const fraction = item.value / total;
            const dash = fraction * circumference;
            const gap = circumference - dash;
            const offset = -offsetAcc;
            offsetAcc += dash;
            const color = colors?.[item.label] ?? PALETTE[idx % PALETTE.length];
            return (
              <circle
                key={item.label}
                cx="55"
                cy="55"
                r={radius}
                fill="none"
                stroke={color}
                strokeWidth="14"
                strokeDasharray={`${dash} ${gap}`}
                strokeDashoffset={offset}
              />
            );
          })}
      </svg>
      <div style={{ display: "flex", flexDirection: "column", gap: "6px", minWidth: "120px" }}>
        {items.map((item, idx) => {
          const color = colors?.[item.label] ?? PALETTE[idx % PALETTE.length];
          const pct = total ? Math.round((item.value / total) * 100) : 0;
          return (
            <div key={item.label} style={{ display: "flex", alignItems: "center", gap: "7px", fontSize: "12px" }}>
              <span style={{ width: "9px", height: "9px", borderRadius: "3px", background: color, flexShrink: 0 }} />
              <span style={{ color: "var(--text-muted)", flex: 1 }}>{item.label}</span>
              <span style={{ fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{item.value}</span>
              <span style={{ color: "var(--text-dim)", fontSize: "10.5px", width: "32px", textAlign: "right" }}>{pct}%</span>
            </div>
          );
        })}
        {items.length === 0 && <p className="muted">Sin datos todavía.</p>}
      </div>
    </div>
  );
}
