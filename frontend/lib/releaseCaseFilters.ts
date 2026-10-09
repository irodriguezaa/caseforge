const storagePrefix = "qcpulse.releaseCaseFilters.v1.";

export type ReleaseCaseFilters = {
  device: string;
  component: string[];
  story: string[];
  priority: string[];
  status: string[];
};

export const EMPTY_RELEASE_CASE_FILTERS: ReleaseCaseFilters = {
  device: "",
  component: [],
  story: [],
  priority: [],
  status: [],
};

function storageKey(releaseId: number): string {
  return `${storagePrefix}${releaseId}`;
}

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
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
      component: asStringList(parsed.component),
      story: asStringList(parsed.story),
      priority: asStringList(parsed.priority),
      status: asStringList(parsed.status),
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
    && filters.component.length === 0
    && filters.story.length === 0
    && filters.priority.length === 0
    && filters.status.length === 0;
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

export function pruneFilterList(selected: string[], options: string[]): string[] {
  if (selected.length === 0 || options.length === 0) {
    return selected;
  }
  const allowed = new Set(options);
  const next = selected.filter((item) => allowed.has(item));
  return next.length === selected.length ? selected : next;
}
