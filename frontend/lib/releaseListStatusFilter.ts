import type { ColumnFilterSelection } from "@/lib/releaseCaseFilters";
import type { ReleaseStatus } from "@/lib/types";

export const OPE_PENDING_STATUS = "PENDIENTE";

export const RELEASE_LIST_STATUS_STORAGE = {
  apps: "qcpulse.releaseList.statusFilter.apps",
  be: "qcpulse.releaseList.statusFilter.be",
  ope: "qcpulse.releaseList.statusFilter.ope",
} as const;

export const RELEASE_LIST_STATUS_OPTIONS: { value: ReleaseStatus; label: string }[] = [
  { value: "DRAFT", label: "DRAFT" },
  { value: "IN_PROGRESS", label: "IN PROGRESS" },
  { value: "COMPLETED", label: "COMPLETED" },
  { value: "CANCELLED", label: "CANCELLED" },
];

export const RELEASE_LIST_STATUS_VALUES: ReleaseStatus[] = RELEASE_LIST_STATUS_OPTIONS.map(
  (item) => item.value,
);

export const OPE_LIST_STATUS_OPTIONS: { value: string; label: string }[] = [
  ...RELEASE_LIST_STATUS_OPTIONS,
  { value: OPE_PENDING_STATUS, label: "Pendiente" },
];

export const OPE_LIST_STATUS_VALUES: string[] = OPE_LIST_STATUS_OPTIONS.map((item) => item.value);

function asSelection(value: unknown, allowed: readonly string[]): ColumnFilterSelection {
  if (value == null || !Array.isArray(value)) {
    return null;
  }
  const allowedSet = new Set(allowed);
  const next = value.filter((item): item is string => typeof item === "string" && allowedSet.has(item));
  if (next.length === allowed.length) {
    return null;
  }
  if (next.length === 0) {
    return value.length === 0 ? [] : null;
  }
  return next;
}

export function loadReleaseListStatusFilter(
  storageKey: string,
  allowed: readonly string[],
): ColumnFilterSelection {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) {
      return null;
    }
    return asSelection(JSON.parse(raw), allowed);
  } catch {
    return null;
  }
}

export function saveReleaseListStatusFilter(
  storageKey: string,
  selected: ColumnFilterSelection,
): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    if (selected === null) {
      window.localStorage.removeItem(storageKey);
      return;
    }
    window.localStorage.setItem(storageKey, JSON.stringify(selected));
  } catch {
    // Private mode / quota: keep the in-memory filter only.
  }
}

export function opeReleaseListStatus(qcStatus: string | null | undefined): string {
  return qcStatus && qcStatus.length > 0 ? qcStatus : OPE_PENDING_STATUS;
}

export function matchesReleaseListStatus(
  rowStatus: string | null | undefined,
  selected: ColumnFilterSelection,
): boolean {
  if (selected === null) {
    return true;
  }
  return selected.includes(rowStatus ?? "");
}

export function statusFilterCaption(
  selected: ColumnFilterSelection,
  options: { value: string; label: string }[],
): string {
  if (selected === null) {
    return "Todos";
  }
  if (selected.length === 0) {
    return "Ninguno";
  }
  const labels = options.filter((item) => selected.includes(item.value)).map((item) => item.label);
  if (labels.length <= 2) {
    return labels.join(", ");
  }
  return `${labels[0]} +${labels.length - 1}`;
}
