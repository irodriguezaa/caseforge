/** QC effort from real Test Cases. Keep in sync with backend `qc_effort`. */

export const QC_HOURS_PER_DAY = 6;
export const BLOCKER_MINUTES = 20;
export const CRITICAL_MINUTES = 15;
export const QC_CASE_MINUTES: Record<string, Record<string, number>> = {
  CRITICAL: { BAJA: 15, LOW: 15, MEDIA: 20, MEDIUM: 20, ALTA: 25, HIGH: 25 },
  BLOCKER: { BAJA: 20, LOW: 20, MEDIA: 30, MEDIUM: 30, ALTA: 40, HIGH: 40 },
};

/** Retired count formula, comparison only: (TC / 46) × 3 days. */
export const QC_CASES_PER_DAY_LEGACY = 46;
export const QC_RELEASE_EFFORT_FACTOR_LEGACY = 3.0;

export const QC_OPERATIVA_CASES_PER_DAY = 6;

export const QC_ESTIMATION_TOOLTIP =
  "Esfuerzo QC en minutos: CRITICAL 15/20/25 y BLOCKER 20/30/40 (BAJA/MEDIA/ALTA). La complejidad sale de pasos/condición/confianza, no de la prioridad. Días-persona = horas / 6. Duración = días-persona / recursos. La ventana de ejecución es calendario y no entra en esta fórmula.";

export const QC_OPERATIVA_ESTIMATION_TOOLTIP =
  "Operativa: 1 tester por dispositivo. Horas = N × (6 h/día ÷ 6 TC/día) = N × 1 h. Días QC = max(casos del dispositivo más cargado) ÷ 6 TC/día (trabajo en paralelo). Filtra un dispositivo para ver tu slice.";

export function priorityBaseMinutes(priority?: string | null): number {
  return String(priority || "").toUpperCase() === "BLOCKER" ? BLOCKER_MINUTES : CRITICAL_MINUTES;
}

function complexityKey(complexity?: string | null): string {
  const key = String(complexity || "MEDIA").trim().toUpperCase();
  if (key in (QC_CASE_MINUTES.CRITICAL || {})) {
    return key;
  }
  return "MEDIA";
}

export function estimateCaseMinutes(priority?: string | null, complexity?: string | null): number {
  const band = String(priority || "").toUpperCase() === "BLOCKER" ? "BLOCKER" : "CRITICAL";
  return QC_CASE_MINUTES[band][complexityKey(complexity)];
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

export function primaryEpicKey(row: {
  component?: string | null;
  hn_source?: string | null;
  technical_epic?: string | null;
}): string {
  const raw = (row.component || row.technical_epic || row.hn_source || "Sin EPC").trim() || "Sin EPC";
  return raw.split("|")[0]?.trim() || "Sin EPC";
}

export type EpicProgressRow = {
  key: string;
  total: number;
  executed: number;
  percent: number;
  hours: number;
};

function caseHours(row: {
  priority?: string | null;
  complexity?: string | null;
  estimation_hours?: number | null;
}): number {
  if (row.estimation_hours != null && Number.isFinite(Number(row.estimation_hours))) {
    return Number(row.estimation_hours);
  }
  return estimateCaseMinutes(row.priority, row.complexity) / 60;
}

export function progressByTechnicalEpic(
  cases: Array<{
    component?: string | null;
    hn_source?: string | null;
    technical_epic?: string | null;
    status?: string | null;
    priority?: string | null;
    complexity?: string | null;
    estimation_hours?: number | null;
  }>,
): EpicProgressRow[] {
  const grouped = new Map<string, { total: number; executed: number; hours: number }>();
  for (const row of cases) {
    const key = primaryEpicKey(row);
    const current = grouped.get(key) || { total: 0, executed: 0, hours: 0 };
    current.total += 1;
    if (String(row.status || "").toUpperCase() !== "UNEXECUTED") {
      current.executed += 1;
    }
    current.hours += caseHours(row);
    grouped.set(key, current);
  }
  return [...grouped.entries()]
    .map(([key, stats]) => ({
      key,
      total: stats.total,
      executed: stats.executed,
      percent: stats.total === 0 ? 0 : Math.round((stats.executed * 1000) / stats.total) / 10,
      hours: Math.round(stats.hours * 10) / 10,
    }))
    .sort((a, b) => b.hours - a.hours || a.key.localeCompare(b.key, "es"));
}

export function hoursByTechnicalEpic(
  cases: Array<{
    component?: string | null;
    hn_source?: string | null;
    technical_epic?: string | null;
    priority?: string | null;
    complexity?: string | null;
    estimation_hours?: number | null;
  }>,
): { label: string; value: number }[] {
  const grouped = new Map<string, number>();
  for (const row of cases) {
    const key = primaryEpicKey(row);
    grouped.set(key, (grouped.get(key) || 0) + caseHours(row));
  }
  return [...grouped.entries()]
    .map(([key, hours]) => ({
      label: key,
      value: Math.round(hours * 10) / 10,
    }))
    .sort((a, b) => b.value - a.value || a.label.localeCompare(b.label, "es"));
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
