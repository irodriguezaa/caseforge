export const MONTH_FULL = [
  "Enero",
  "Febrero",
  "Marzo",
  "Abril",
  "Mayo",
  "Junio",
  "Julio",
  "Agosto",
  "Septiembre",
  "Octubre",
  "Noviembre",
  "Diciembre",
] as const;

export const MONTH_AXIS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"] as const;

export const MUNDIAL_MONTH_KEY = "2026-06";

export const PRIORITY_CATEGORIES = ["BLOCKER", "CRITICAL", "OTHER"] as const;

export const PRIORITY_LABELS: Record<string, string> = {
  BLOCKER: "Blocker",
  CRITICAL: "Crítica",
  OTHER: "Otros",
};

export const KPI_PRIORITY_COLORS: Record<string, string> = {
  BLOCKER: "var(--kpi-blocker)",
  CRITICAL: "var(--kpi-critical)",
  OTHER: "var(--kpi-other)",
};

export const KPI_CATEGORY_PALETTE = [
  "var(--kpi-cat-1)",
  "var(--kpi-cat-2)",
  "var(--kpi-cat-3)",
  "var(--kpi-cat-4)",
  "var(--kpi-cat-5)",
  "var(--kpi-cat-6)",
  "var(--kpi-cat-7)",
];

const MONTH_KEY = /^(\d{4})-(\d{2})$/;

export function isMonthKey(key: string): boolean {
  return MONTH_KEY.test(key);
}

export function monthFullName(key: string): string {
  const match = MONTH_KEY.exec(key);
  if (!match) return key;
  const idx = Number(match[2]) - 1;
  return MONTH_FULL[idx] ?? key;
}

export function monthAxisLabel(key: string): string {
  const match = MONTH_KEY.exec(key);
  if (!match) return key;
  const idx = Number(match[2]) - 1;
  return MONTH_AXIS[idx] ?? key;
}

export function isMundialMonth(key: string): boolean {
  return key === MUNDIAL_MONTH_KEY;
}

export type ChartFilterKind = "swf" | "device" | "cluster" | "program";

export interface ChartFilter {
  kind: ChartFilterKind;
  value: string;
}

export const FILTER_KIND_LABEL: Record<ChartFilterKind, string> = {
  swf: "SWF",
  device: "Dispositivo",
  cluster: "Cluster",
  program: "Programa",
};

export type ReleaseBugScope = "QC" | "QA" | "QC_QA";
