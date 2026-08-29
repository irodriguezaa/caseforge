// Cluster vocabulary.
export const CLUSTERS = ["AUP", "Andina", "CENAM", "Dominicana", "Global"] as const;
export const RELEASE_CLUSTER_OPTIONS = ["Todos", "AUP", "Andina", "CENAM", "Dominicana", "Global"] as const;

// Exact 17 device options for Release Note & Release cycle
export const DEVICE_OPTIONS = [
  "WEB",
  "ADR",
  "ADT",
  "FireTv",
  "AAF Evolutivo",
  "AAF Legacy",
  "STB IPTV",
  "STV Tata Samsung",
  "STV Tata Hisense",
  "STV Tata LG",
  "STV Tata ADT",
  "WIN/XBOX",
  "Coship9085",
  "iOS",
  "tvOS",
  "Kepler",
  "IPTV AOSP",
] as const;

export const VALIDATION_TYPE_OPTIONS = ["Smoke", "Completo"] as const;

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
