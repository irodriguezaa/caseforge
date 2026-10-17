"use client";

import { ColumnFilter } from "@/app/components/ColumnFilter";
import type { ColumnFilterSelection } from "@/lib/releaseCaseFilters";
import {
  OPE_LIST_STATUS_OPTIONS,
  RELEASE_LIST_STATUS_OPTIONS,
  statusFilterCaption,
} from "@/lib/releaseListStatusFilter";

interface StatusListFilterProps {
  selected: ColumnFilterSelection;
  onChange: (next: ColumnFilterSelection) => void;
  includePending?: boolean;
}

export function StatusListFilter({
  selected,
  onChange,
  includePending = false,
}: StatusListFilterProps): React.ReactElement {
  const options = includePending ? OPE_LIST_STATUS_OPTIONS : RELEASE_LIST_STATUS_OPTIONS;
  const values = options.map((item) => item.value);
  const labels = new Map(options.map((item) => [item.value, item.label]));

  return (
    <div className="muted" style={{ display: "flex", alignItems: "center", gap: "8px" }}>
      Estado
      <ColumnFilter
        label={statusFilterCaption(selected, options)}
        ariaLabel="Filtrar Estado"
        options={values}
        selected={selected}
        onChange={onChange}
        formatOption={(value) => labels.get(value) ?? value}
      />
    </div>
  );
}
