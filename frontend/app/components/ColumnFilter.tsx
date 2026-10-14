"use client";

import { ChevronDown } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { ColumnFilterSelection } from "@/lib/releaseCaseFilters";

export type { ColumnFilterSelection };

interface ColumnFilterProps {
  label: string;
  options: string[];
  selected: ColumnFilterSelection;
  onChange: (next: ColumnFilterSelection) => void;
  formatOption?: (value: string) => string;
}

function placeMenu(button: HTMLElement, menu: HTMLElement): void {
  const rect = button.getBoundingClientRect();
  const menuHeight = menu.offsetHeight;
  const menuWidth = Math.max(220, Math.min(320, menu.offsetWidth || 220));
  const spaceBelow = window.innerHeight - rect.bottom;
  const top =
    spaceBelow < menuHeight + 8 && rect.top > menuHeight + 8
      ? rect.top - menuHeight - 6
      : rect.bottom + 6;
  let left = rect.left;
  if (left + menuWidth > window.innerWidth - 8) {
    left = Math.max(8, window.innerWidth - menuWidth - 8);
  }
  menu.style.top = `${Math.max(8, top)}px`;
  menu.style.left = `${left}px`;
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
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuScrollTop = useRef(0);
  const lockScrollY = useRef<number | null>(null);
  const selectedSet = new Set(selected ?? []);
  const allChecked = selected === null || (options.length > 0 && selected.length === options.length);
  const active = !allChecked;

  useEffect(() => {
    if (!open) {
      return;
    }
    function onPointerDown(event: MouseEvent): void {
      const target = event.target as Node;
      if (rootRef.current?.contains(target) || menuRef.current?.contains(target)) {
        return;
      }
      setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  useLayoutEffect(() => {
    if (lockScrollY.current != null) {
      window.scrollTo({ top: lockScrollY.current, left: 0, behavior: "instant" });
      lockScrollY.current = null;
    }
    const button = buttonRef.current;
    const menu = menuRef.current;
    if (!open || !button || !menu) {
      return;
    }
    function sync(): void {
      if (button && menu) {
        placeMenu(button, menu);
        menu.scrollTop = menuScrollTop.current;
      }
    }
    sync();
    window.addEventListener("scroll", sync, true);
    window.addEventListener("resize", sync);
    return () => {
      window.removeEventListener("scroll", sync, true);
      window.removeEventListener("resize", sync);
    };
  }, [open, selected, options.length]);

  function applyFilter(next: ColumnFilterSelection): void {
    menuScrollTop.current = menuRef.current?.scrollTop ?? 0;
    lockScrollY.current = window.scrollY;
    onChange(next);
  }

  function toggleAll(): void {
    applyFilter(allChecked ? [] : null);
  }

  function toggleValue(value: string): void {
    if (allChecked) {
      applyFilter(options.filter((item) => item !== value));
      return;
    }
    const current = selected ?? [];
    if (selectedSet.has(value)) {
      applyFilter(current.filter((item) => item !== value));
      return;
    }
    const next = [...current, value];
    applyFilter(next.length === options.length ? null : next);
  }

  const caption = formatOption ?? ((value: string) => value);

  const menu = open ? (
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
  ) : null;

  return (
    <div ref={rootRef} className="col-filter">
      <button
        ref={buttonRef}
        type="button"
        className={`col-filter-btn${active ? " is-on" : ""}`}
        aria-expanded={open}
        aria-label={`Filtrar ${label}`}
        onClick={() => setOpen((value) => !value)}
      >
        <span>{label}</span>
        <ChevronDown size={14} aria-hidden="true" />
      </button>
      {menu && typeof document !== "undefined" ? createPortal(menu, document.body) : null}
    </div>
  );
}
