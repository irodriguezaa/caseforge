export function BarList({
  items,
  color = "var(--accent)",
  formatValue,
  wideLabels = false,
  hrefForLabel,
}: {
  items: { label: string; value: number }[];
  color?: string;
  formatValue?: (value: number) => string;
  wideLabels?: boolean;
  hrefForLabel?: (label: string) => string | null;
}): React.ReactElement {
  const max = Math.max(1, ...items.map((i) => i.value));
  return (
    <div className={`bar-list${wideLabels ? " bar-list-wide" : ""}`}>
      {items.map((item) => {
        const href = hrefForLabel?.(item.label) ?? null;
        return (
          <div className="bar-row" key={item.label}>
            {href ? (
              <a className="bar-label" href={href} target="_blank" rel="noopener noreferrer" title={`Abrir ${item.label} en Jira`}>
                {item.label}
              </a>
            ) : (
              <span className="bar-label" title={item.label}>{item.label}</span>
            )}
            <div className="bar-track">
              <div className="bar-fill" style={{ width: `${(item.value / max) * 100}%`, background: color }} />
            </div>
            <span className="bar-value">{formatValue ? formatValue(item.value) : item.value}</span>
          </div>
        );
      })}
      {items.length === 0 && <p className="muted">Sin datos todavía.</p>}
    </div>
  );
}
