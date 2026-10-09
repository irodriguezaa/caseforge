"use client";

import { ChevronDown } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { ColumnFilterSelection } from "@/lib/releaseCaseFilters";

export type { ColumnFilterSelection };

interface ColumnFilterProps {
  label: string;
  options: string[];
  selected: ColumnFilterSelection;
  onChange: (next: ColumnFilterSelection) => void;
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
  const menuRef = useRef<HTMLDivElement>(null);
  const menuScrollTop = useRef(0);
  const selectedSet = new Set(selected ?? []);
  const allChecked = selected === null || (options.length > 0 && selected.length === options.length);
  const active = !allChecked;

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

  useLayoutEffect(() => {
    if (menuRef.current) {
      menuRef.current.scrollTop = menuScrollTop.current;
    }
  }, [selected, open]);

  function keepMenuScroll(): void {
    menuScrollTop.current = menuRef.current?.scrollTop ?? 0;
  }

  function toggleAll(): void {
    keepMenuScroll();
    onChange(allChecked ? [] : null);
  }

  function toggleValue(value: string): void {
    keepMenuScroll();
    if (allChecked) {
      onChange(options.filter((item) => item !== value));
      return;
    }
    const current = selected ?? [];
    if (selectedSet.has(value)) {
      onChange(current.filter((item) => item !== value));
      return;
    }
    const next = [...current, value];
    onChange(next.length === options.length ? null : next);
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
        <div
          ref={menuRef}
          className="col-filter-menu"
          role="listbox"
          aria-label={label}
          onMouseDown={(event) => event.preventDefault()}
        >
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
