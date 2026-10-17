"use client";

import { useEffect, useRef, useState } from "react";
import type { ColumnFilterSelection } from "@/lib/releaseCaseFilters";
import {
  loadReleaseListStatusFilter,
  saveReleaseListStatusFilter,
} from "@/lib/releaseListStatusFilter";

export function usePersistedStatusFilter(
  storageKey: string,
  allowedValues: readonly string[],
): [ColumnFilterSelection, (next: ColumnFilterSelection) => void] {
  const [selected, setSelected] = useState<ColumnFilterSelection>(null);
  const skipSave = useRef(true);

  useEffect(() => {
    skipSave.current = true;
    setSelected(loadReleaseListStatusFilter(storageKey, allowedValues));
  }, [storageKey, allowedValues]);

  useEffect(() => {
    if (skipSave.current) {
      skipSave.current = false;
      return;
    }
    saveReleaseListStatusFilter(storageKey, selected);
  }, [storageKey, selected]);

  return [selected, setSelected];
}
