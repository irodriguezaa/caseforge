/**
 * Alcance de validación de Release App.
 * Se guarda tal cual en releases.validation_type (texto libre, varchar 50).
 * No hay enum: un valor histórico (Completo, Smoke, Funcional, Exploratorio, NA, …)
 * se conserva y no se reescribe al catálogo nuevo.
 *
 * Integración pendiente con la matriz QC — no implementada:
 * el alcance debería elegir qué filas de la matriz del dispositivo, plataforma y producto
 * complementan los casos de CaseForge, comparando comportamiento y sin duplicar cobertura.
 * Pruebas Acotadas: conjunto específico del cambio.
 * Smoke Test: funcionalidades críticas y principales.
 * Regresivo: funcionalidades modificadas o relacionadas.
 * No Afectación: funcionalidades que no deberían verse afectadas.
 * Regresión completa: unión de Regresivo y No Afectación, con su propia estimación (no la suma).
 * N/A: no incorpora casos de matriz por este concepto.
 */

export type ValidationScopeEstimate = {
  /** Texto operativo definido por QC. No sale de la fórmula de casos. */
  label: string;
};

export type ValidationScope = {
  label: string;
  description: string;
  /** null: este alcance no tiene esfuerzo de validación. */
  estimate: ValidationScopeEstimate | null;
};

export const VALIDATION_SCOPES: readonly ValidationScope[] = [
  {
    label: "Pruebas Acotadas",
    description:
      "Validación de un conjunto específico y limitado de funcionalidades, definido de acuerdo con el alcance del cambio o la necesidad de la prueba, sin ejecutar la cobertura completa.",
    estimate: { label: "2 horas" },
  },
  {
    label: "Smoke Test",
    description:
      "Validación rápida de las funcionalidades críticas y principales del producto, con el objetivo de confirmar la estabilidad básica de la versión.",
    estimate: { label: "3 horas" },
  },
  {
    label: "Regresivo",
    description:
      "Validación de las funcionalidades o módulos que fueron modificados o que tienen una relación directa con el cambio, con el objetivo de verificar que este no haya introducido defectos.",
    estimate: { label: "Aproximadamente 3–4 horas" },
  },
  {
    label: "No Afectación",
    description:
      "Validación de funcionalidades o módulos que no deberían verse afectados por el cambio, con el objetivo de confirmar que continúan operando correctamente.",
    estimate: { label: "Aproximadamente 3–4 horas" },
  },
  {
    label: "Regresión completa",
    description:
      "Validación integral de las funcionalidades del producto, incluyendo las funcionalidades modificadas o relacionadas directamente con el cambio y aquellas que no deberían verse afectadas, con el objetivo de verificar que la versión mantiene su comportamiento esperado y que no se introdujeron defectos.",
    estimate: { label: "Aproximadamente 6–8 horas" },
  },
  {
    label: "N/A",
    description: "No aplica.",
    estimate: null,
  },
] as const;

const SCOPE_BY_LABEL = new Map(VALIDATION_SCOPES.map((scope) => [scope.label, scope]));

export function validationScopeByLabel(value: string | null | undefined): ValidationScope | null {
  const key = (value ?? "").trim();
  if (!key) return null;
  return SCOPE_BY_LABEL.get(key) ?? null;
}

/** Catálogo en el orden definido. Un valor guardado fuera del catálogo se agrega al final, sin reescribirlo. */
export function validationScopeChoices(current: string | null | undefined): string[] {
  const labels = VALIDATION_SCOPES.map((scope) => scope.label);
  const value = (current ?? "").trim();
  if (value && !labels.includes(value)) {
    return [...labels, value];
  }
  return labels;
}
