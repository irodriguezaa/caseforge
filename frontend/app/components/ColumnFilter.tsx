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
  const menuWidth = Math.max(220, Math.min(320, menu.offsetWidth || 220));
  const spaceBelow = Math.max(120, window.innerHeight - rect.bottom - 12);
  menu.style.maxHeight = `${Math.min(280, spaceBelow)}px`;
  let left = rect.left;
  if (left + menuWidth > window.innerWidth - 8) {
    left = Math.max(8, window.innerWidth - menuWidth - 8);
  }
  menu.style.top = `${rect.bottom + 6}px`;
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
  const lockButtonTop = useRef<number | null>(null);
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
    const button = buttonRef.current;
    if (lockButtonTop.current != null && button) {
      window.scrollBy({ top: button.getBoundingClientRect().top - lockButtonTop.current, left: 0, behavior: "instant" });
      lockButtonTop.current = null;
    }
    const menu = menuRef.current;
    if (!open || !button || !menu) {
      return;
    }
    const trigger = button;
    const panel = menu;
    placeMenu(trigger, panel);
    panel.scrollTop = menuScrollTop.current;
    function onScroll(event: Event): void {
      if (panel.contains(event.target as Node)) {
        return;
      }
      placeMenu(trigger, panel);
    }
    function onResize(): void {
      placeMenu(trigger, panel);
    }
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onResize);
    };
  }, [open, selected, options.length]);

  function applyFilter(next: ColumnFilterSelection): void {
    menuScrollTop.current = menuRef.current?.scrollTop ?? 0;
    lockButtonTop.current = buttonRef.current?.getBoundingClientRect().top ?? null;
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
      onScroll={(event) => {
        menuScrollTop.current = event.currentTarget.scrollTop;
      }}
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
