"use client";

import { useState } from "react";

export function InfoTooltip({ text }: { text: string }): React.ReactElement {
  const [open, setOpen] = useState(false);
  return (
    <span
      style={{ position: "relative", display: "inline-flex", verticalAlign: "middle", marginLeft: "5px" }}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <span
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          width: "14px",
          height: "14px",
          borderRadius: "50%",
          border: "1px solid var(--text-dim)",
          color: "var(--text-dim)",
          fontSize: "9.5px",
          fontStyle: "italic",
          fontWeight: 600,
          cursor: "help",
        }}
      >
        i
      </span>
      {open && (
        <span
          role="tooltip"
          style={{
            position: "absolute",
            bottom: "22px",
            left: "50%",
            transform: "translateX(-50%)",
            width: "240px",
            background: "var(--surface-2)",
            border: "1px solid var(--border)",
            borderRadius: "8px",
            padding: "9px 11px",
            fontSize: "11px",
            lineHeight: "1.45",
            color: "var(--text-muted)",
            fontWeight: 400,
            textTransform: "none",
            letterSpacing: "normal",
            zIndex: 20,
            boxShadow: "0 4px 16px rgba(0,0,0,.35)",
          }}
        >
          {text}
        </span>
      )}
    </span>
  );
}
