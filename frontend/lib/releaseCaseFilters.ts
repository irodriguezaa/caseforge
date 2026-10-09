export type ColumnFilterSelection = string[] | null;

const storagePrefix = "qcpulse.releaseCaseFilters.v2.";

export type ReleaseCaseFilters = {
  device: string;
  component: ColumnFilterSelection;
  story: ColumnFilterSelection;
  priority: ColumnFilterSelection;
  status: ColumnFilterSelection;
};

export const EMPTY_RELEASE_CASE_FILTERS: ReleaseCaseFilters = {
  device: "",
  component: null,
  story: null,
  priority: null,
  status: null,
};

function storageKey(releaseId: number): string {
  return `${storagePrefix}${releaseId}`;
}

function asSelection(value: unknown): ColumnFilterSelection {
  if (value == null) {
    return null;
  }
  if (!Array.isArray(value)) {
    return null;
  }
  return value.filter((item): item is string => typeof item === "string" && item.length > 0);
}

export function loadReleaseCaseFilters(releaseId: number): ReleaseCaseFilters {
  if (typeof window === "undefined" || !Number.isFinite(releaseId) || releaseId <= 0) {
    return EMPTY_RELEASE_CASE_FILTERS;
  }
  try {
    const raw = window.sessionStorage.getItem(storageKey(releaseId));
    if (!raw) {
      return EMPTY_RELEASE_CASE_FILTERS;
    }
    const parsed = JSON.parse(raw) as Partial<ReleaseCaseFilters>;
    return {
      device: typeof parsed.device === "string" ? parsed.device : "",
      component: asSelection(parsed.component),
      story: asSelection(parsed.story),
      priority: asSelection(parsed.priority),
      status: asSelection(parsed.status),
    };
  } catch {
    return EMPTY_RELEASE_CASE_FILTERS;
  }
}

export function saveReleaseCaseFilters(releaseId: number, filters: ReleaseCaseFilters): void {
  if (typeof window === "undefined" || !Number.isFinite(releaseId) || releaseId <= 0) {
    return;
  }
  const empty =
    !filters.device
    && filters.component === null
    && filters.story === null
    && filters.priority === null
    && filters.status === null;
  try {
    if (empty) {
      window.sessionStorage.removeItem(storageKey(releaseId));
      return;
    }
    window.sessionStorage.setItem(storageKey(releaseId), JSON.stringify(filters));
  } catch {
    // Private mode / quota: keep the in-memory filters only.
  }
}

export function pruneFilterList(
  selected: ColumnFilterSelection,
  options: string[],
): ColumnFilterSelection {
  if (selected === null || options.length === 0) {
    return selected;
  }
  const allowed = new Set(options);
  const next = selected.filter((item) => allowed.has(item));
  if (next.length === options.length) {
    return null;
  }
  return next.length === selected.length ? selected : next;
}

export function columnFilterIsActive(selected: ColumnFilterSelection): boolean {
  return selected !== null;
}
