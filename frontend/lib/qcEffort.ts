/** QC effort from real Test Cases. Keep in sync with backend `qc_effort`. */

export const QC_HOURS_PER_DAY = 6;
export const BLOCKER_MINUTES = 20;
export const CRITICAL_MINUTES = 12;
export const COMPLEXITY_FACTOR: Record<string, number> = {
  BAJA: 1.0,
  LOW: 1.0,
  MEDIA: 1.3,
  MEDIUM: 1.3,
  ALTA: 1.6,
  HIGH: 1.6,
};

/** Retired count formula, comparison only: (TC / 46) × 3 days. */
export const QC_CASES_PER_DAY_LEGACY = 46;
export const QC_RELEASE_EFFORT_FACTOR_LEGACY = 3.0;

export const QC_OPERATIVA_CASES_PER_DAY = 6;

export const QC_ESTIMATION_TOOLTIP =
  "Esfuerzo QC = minutos base (BLOCKER 20 / CRITICAL 12) × factor (BAJA 1.0 / MEDIA 1.3 / ALTA 1.6). La complejidad sale de pasos/condición/confianza, no de la prioridad. Días-persona = horas / 6. Duración = días-persona / recursos. La ventana de ejecución es calendario y no entra en esta fórmula.";

export const QC_OPERATIVA_ESTIMATION_TOOLTIP =
  "Operativa: 1 tester por dispositivo. Horas = N × (6 h/día ÷ 6 TC/día) = N × 1 h. Días QC = max(casos del dispositivo más cargado) ÷ 6 TC/día (trabajo en paralelo). Filtra un dispositivo para ver tu slice.";

export function priorityBaseMinutes(priority?: string | null): number {
  return String(priority || "").toUpperCase() === "BLOCKER" ? BLOCKER_MINUTES : CRITICAL_MINUTES;
}

export function complexityFactor(complexity?: string | null): number {
  const key = String(complexity || "MEDIA").trim().toUpperCase();
  return COMPLEXITY_FACTOR[key] ?? COMPLEXITY_FACTOR.MEDIA;
}

export function estimateCaseMinutes(priority?: string | null, complexity?: string | null): number {
  return Math.round(priorityBaseMinutes(priority) * complexityFactor(complexity) * 10) / 10;
}

export function estimateReleaseEffortFromCases(
  cases: Array<{ priority?: string | null; complexity?: string | null }>,
): { hours: number; days: number; minutes: number } {
  if (!cases.length) {
    return { hours: 0, days: 0, minutes: 0 };
  }
  const minutes = cases.reduce((sum, row) => sum + estimateCaseMinutes(row.priority, row.complexity), 0);
  const realHours = minutes / 60;
  const days = realHours / QC_HOURS_PER_DAY;
  return {
    minutes,
    hours: Math.round(realHours * 10) / 10,
    days: Math.round(days * 10) / 10,
  };
}

export function durationDays(personDays: number, resources: number): number {
  const testers = Math.max(1, Math.floor(resources) || 1);
  return Math.round((personDays / testers) * 10) / 10;
}

export function estimateReleaseEffortLegacyCount(testCaseCount: number): { hours: number; days: number } {
  const count = Math.max(0, Math.floor(testCaseCount));
  if (count === 0) {
    return { hours: 0, days: 0 };
  }
  const days = (count / QC_CASES_PER_DAY_LEGACY) * QC_RELEASE_EFFORT_FACTOR_LEGACY;
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
