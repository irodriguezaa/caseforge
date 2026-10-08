"use client";

import { ChevronDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";

interface ColumnFilterProps {
  label: string;
  options: string[];
  selected: string[];
  onChange: (next: string[]) => void;
  formatOption?: (value: string) => string;
}

export function ColumnFilter({
  label,
  options,
  selected,
  onChange,
  formatOption,
}: ColumnFilterProps): React.ReactElement {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const active = selected.length > 0;
  const selectedSet = new Set(selected);
  const allChecked = !active;

  useEffect(() => {
    if (!open) {
      return;
    }
    function onPointerDown(event: MouseEvent): void {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  function toggleAll(): void {
    onChange([]);
  }

  function toggleValue(value: string): void {
    if (allChecked) {
      onChange(options.filter((item) => item !== value));
      return;
    }
    if (selectedSet.has(value)) {
      const next = selected.filter((item) => item !== value);
      onChange(next.length === options.length ? [] : next);
      return;
    }
    const next = [...selected, value];
    onChange(next.length === options.length ? [] : next);
  }

  const caption = formatOption ?? ((value: string) => value);

  return (
    <div ref={rootRef} className="col-filter">
      <button
        type="button"
        className={`col-filter-btn${active ? " is-on" : ""}`}
        aria-expanded={open}
        aria-label={`Filtrar ${label}`}
        onClick={() => setOpen((value) => !value)}
      >
        <span>{label}</span>
        <ChevronDown size={14} aria-hidden="true" />
      </button>
      {open ? (
        <div className="col-filter-menu" role="listbox" aria-label={label}>
          <label className="col-filter-item">
            <input type="checkbox" checked={allChecked} onChange={toggleAll} />
            (Todos)
          </label>
          {options.map((option) => (
            <label key={option} className="col-filter-item">
              <input
                type="checkbox"
                checked={allChecked || selectedSet.has(option)}
                onChange={() => toggleValue(option)}
              />
              {caption(option)}
            </label>
          ))}
        </div>
      ) : null}
    </div>
  );
}
