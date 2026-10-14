import type { TestCase } from "@/lib/types";
import type { ColumnFilterSelection } from "@/lib/releaseCaseFilters";

export interface CaseListFilters {
  device: string;
  component: ColumnFilterSelection;
  story: ColumnFilterSelection;
  priority: ColumnFilterSelection;
  status: ColumnFilterSelection;
}

export function componentLabel(row: TestCase): string {
  return (row.component || row.technical_epic || "").trim();
}

export function storyLabel(row: TestCase): string {
  return (row.technical_story || "").trim();
}

export function filterReleaseCases(rows: TestCase[], filters: CaseListFilters): TestCase[] {
  const components = filters.component === null ? null : new Set(filters.component);
  const stories = filters.story === null ? null : new Set(filters.story);
  const priorities = filters.priority === null ? null : new Set(filters.priority);
  const statuses = filters.status === null ? null : new Set(filters.status);
  return rows.filter((row) => {
    if (filters.device && (row.device || "").trim() !== filters.device) {
      return false;
    }
    if (components && !components.has(componentLabel(row))) {
      return false;
    }
    if (stories && !stories.has(storyLabel(row))) {
      return false;
    }
    if (priorities && !priorities.has(row.priority)) {
      return false;
    }
    if (statuses && !statuses.has(row.status)) {
      return false;
    }
    return true;
  });
}

export function toggleSelectedId(selected: number[], id: number): number[] {
  return selected.includes(id) ? selected.filter((item) => item !== id) : [...selected, id];
}

export function selectFilteredIds(rows: TestCase[]): number[] {
  return rows.map((row) => row.id);
}

export function headerCheckboxState(
  visibleIds: number[],
  selectedIds: number[],
): { checked: boolean; indeterminate: boolean } {
  if (visibleIds.length === 0) {
    return { checked: false, indeterminate: false };
  }
  const selected = new Set(selectedIds);
  const selectedVisible = visibleIds.filter((id) => selected.has(id)).length;
  return {
    checked: selectedVisible === visibleIds.length,
    indeterminate: selectedVisible > 0 && selectedVisible < visibleIds.length,
  };
}

export function summarizeBulkResult(kind: "status" | "delete", ok: number, failed: { id: number; test_case_id?: string | null; message: string }[]): string {
  const verb = kind === "status" ? "actualizó" : "eliminó";
  const verbPlural = kind === "status" ? "actualizaron" : "eliminaron";
  if (failed.length === 0) {
    return `Se ${ok === 1 ? verb : verbPlural} ${ok} caso${ok === 1 ? "" : "s"} de prueba.`;
  }
  const details = failed
    .map((item) => `${item.test_case_id || `#${item.id}`}: ${item.message}`)
    .join(" ");
  if (ok === 0) {
    return `No se pudo completar la operación. ${details}`;
  }
  return `Se ${verbPlural} ${ok} caso${ok === 1 ? "" : "s"} y fallaron ${failed.length}. ${details}`;
}
