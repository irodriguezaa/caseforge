"use client";

export function InfoTip({ text }: { text: string }): React.ReactElement {
  return (
    <span className="kpi-info-tip">
      <span className="kpi-info-icon" tabIndex={0} aria-label="Más información">
        ⓘ
      </span>
      <span className="kpi-info-bubble" role="tooltip">
        {text}
      </span>
    </span>
  );
}
