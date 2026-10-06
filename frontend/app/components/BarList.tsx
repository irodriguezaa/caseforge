export function BarList({
  items,
  color = "var(--accent)",
  formatValue,
  wideLabels = false,
}: {
  items: { label: string; value: number }[];
  color?: string;
  formatValue?: (value: number) => string;
  wideLabels?: boolean;
}): React.ReactElement {
  const max = Math.max(1, ...items.map((i) => i.value));
  return (
    <div className={`bar-list${wideLabels ? " bar-list-wide" : ""}`}>
      {items.map((item) => (
        <div className="bar-row" key={item.label}>
          <span className="bar-label" title={item.label}>{item.label}</span>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${(item.value / max) * 100}%`, background: color }} />
          </div>
          <span className="bar-value">{formatValue ? formatValue(item.value) : item.value}</span>
        </div>
      ))}
      {items.length === 0 && <p className="muted">Sin datos todavía.</p>}
    </div>
  );
}
