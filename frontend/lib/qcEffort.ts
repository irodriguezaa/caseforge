/** Homologated QC effort indicator. Keep defaults in sync with backend `qc_effort` / Settings. */
export const QC_CASES_PER_DAY = 46;
export const QC_RELEASE_EFFORT_FACTOR = 3.0;
export const QC_HOURS_PER_DAY = 6;

/**
 * Operativa throughput per tester (one tester = one device).
 * 6 TC/día con jornada de 6 h ⇒ ~1 h por caso.
 * Ajusta este número para cambiar días: días = max(casos por dispositivo) / QC_OPERATIVA_CASES_PER_DAY.
 * Ejemplo 180 TC / 10 dispositivos (18 c/u): horas = 180 × 1 h = 180 h, días = 18 / 6 = 3.0.
 */
export const QC_OPERATIVA_CASES_PER_DAY = 6;

export const QC_ESTIMATION_TOOLTIP =
  "Estimación basada en capacidad estándar de 46 TC/día, factor de esfuerzo integral de Release (3x) y jornada QC de 6 h/día.";

export const QC_OPERATIVA_ESTIMATION_TOOLTIP =
  "Operativa: 1 tester por dispositivo. Horas = N × (6 h/día ÷ 6 TC/día) = N × 1 h. Días QC = max(casos del dispositivo más cargado) ÷ 6 TC/día (trabajo en paralelo). Filtra un dispositivo para ver tu slice.";

export function estimateReleaseEffort(testCaseCount: number): { hours: number; days: number } {
  const count = Math.max(0, Math.floor(testCaseCount));
  if (count === 0) {
    return { hours: 0, days: 0 };
  }
  const days = (count / QC_CASES_PER_DAY) * QC_RELEASE_EFFORT_FACTOR;
  const hours = days * QC_HOURS_PER_DAY;
  return {
    hours: Math.round(hours * 10) / 10,
    days: Math.round(days * 10) / 10,
  };
}

export function estimateOperativaEffort(cases: Array<{ device?: string | null }>): { hours: number; days: number } {
  const count = cases.length;
  if (count === 0) {
    return { hours: 0, days: 0 };
  }
  const byDevice = new Map<string, number>();
  for (const row of cases) {
    const key = (row.device || "").trim() || "Sin dispositivo";
    byDevice.set(key, (byDevice.get(key) || 0) + 1);
  }
  let busiest = 0;
  for (const n of byDevice.values()) {
    busiest = Math.max(busiest, n);
  }
  const hoursPerCase = QC_HOURS_PER_DAY / QC_OPERATIVA_CASES_PER_DAY;
  const hours = Math.round(count * hoursPerCase * 10) / 10;
  const days = Math.round((busiest / QC_OPERATIVA_CASES_PER_DAY) * 10) / 10;
  return { hours, days };
}

export function stripDeviceFromCaseName(name: string, device?: string | null): string {
  const label = (device || "").trim();
  if (!name || !label) {
    return name;
  }
  const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return name.replace(new RegExp(`(?:\\s*[·•|]\\s*|\\s+-\\s+)${escaped}\\s*$`, "i"), "").trim() || name;
}
