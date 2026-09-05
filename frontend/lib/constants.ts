// Cluster vocabulary. Split into two lists because this round of adjustments made "Todos" a
// real, storable Release value (a release can apply company-wide), while the Dashboard's
// cluster FILTER intentionally excludes "Todos" (see product instructions) -- so the two lists
// are no longer the same set.
export const CLUSTERS = ["AUP", "Andina", "CENAM", "Dominicana", "Global"] as const;
export const RELEASE_CLUSTER_OPTIONS = [...CLUSTERS, "Todos"] as const;

export const MONTHS = [
  { value: "01", label: "Enero" },
  { value: "02", label: "Febrero" },
  { value: "03", label: "Marzo" },
  { value: "04", label: "Abril" },
  { value: "05", label: "Mayo" },
  { value: "06", label: "Junio" },
  { value: "07", label: "Julio" },
  { value: "08", label: "Agosto" },
  { value: "09", label: "Septiembre" },
  { value: "10", label: "Octubre" },
  { value: "11", label: "Noviembre" },
  { value: "12", label: "Diciembre" },
] as const;

// SANDBOX-ONLY STUB: not part of this deliverable. Your real constants.ts already has these
// (referenced by releases/page.tsx) -- this exists purely so `tsc`/`build` can validate the
// NEW code in this round without your actual values, which I was not given.
export const DEVICE_OPTIONS = [
  "WEB", "ADR", "ADT", "FireTV", "Roku", "AAF Evolutivo", "AAF Legacy", "STB IPTV",
  "STV Tata Samsung", "STV Tata Hisense", "STV Tata LG", "STV Tata ADT",
  "WIN/XBOX", "Coship9085", "iOS", "tvOS", "Kepler", "IPTV AOSP",
] as const;
export const VALIDATION_TYPE_OPTIONS = ["Completo", "Smoke", "Regresivo", "Funcional", "Exploratorio", "NA"] as const;

export const BE_SWF_OPTIONS = ["Neoris", "Tata", "Hitss"] as const;
export const BE_REGRESIVO_SCOPES = ["COMPLETO", "SMOKE", "ACOTADO"] as const;
export const BE_REGRESIVO_SCOPE_LABEL: Record<(typeof BE_REGRESIVO_SCOPES)[number], string> = {
  COMPLETO: "Completo",
  SMOKE: "Smoke",
  ACOTADO: "Acotado",
};

/** QCO_ZEPHYR_PUBLISH — UI oculta. Código vivo: POST /publish-qco, zephyr_publish, zephyr_mapping.
 *  Retomar cuando QC defina formato Zephyr (Scale), no issues QCO/Test provisionales. */
export const SHOW_QCO_ZEPHYR_PUBLISH = false;
