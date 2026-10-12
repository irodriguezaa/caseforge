"use client";

import {
  VALIDATION_SCOPES,
  validationScopeByLabel,
  validationScopeChoices,
} from "@/lib/validationScope";

type ValidationScopeSelectProps = {
  id: string;
  value: string;
  helpId: string;
  onChange: (value: string) => void;
  style?: React.CSSProperties;
};

export function ValidationScopeSelect({
  id,
  value,
  helpId,
  onChange,
  style,
}: ValidationScopeSelectProps): React.ReactElement {
  const choices = validationScopeChoices(value);
  return (
    <select
      id={id}
      value={value}
      aria-describedby={helpId}
      style={style}
      onChange={(event) => onChange(event.target.value)}
    >
      {value.trim() === "" ? <option value="">Sin alcance guardado</option> : null}
      {choices.map((label) => {
        const scope = validationScopeByLabel(label);
        const historical = !scope && label.trim() !== "";
        return (
          <option key={label} value={label} title={scope?.description ?? "Valor histórico conservado."}>
            {historical ? `${label} (histórico)` : label}
          </option>
        );
      })}
    </select>
  );
}

type ValidationScopeSummaryProps = {
  id: string;
  value: string | null | undefined;
  qcResources?: number | null;
  matrixCaseCount?: number | null;
  matrixNote?: string | null;
  hideEstimate?: boolean;
};

export function ValidationScopeSummary({
  id,
  value,
  qcResources,
  matrixCaseCount,
  matrixNote,
  hideEstimate = false,
}: ValidationScopeSummaryProps): React.ReactElement {
  const stored = (value ?? "").trim();
  const scope = validationScopeByLabel(stored);
  const resources = Math.max(1, Number(qcResources) || 1);
  const knownLabels = VALIDATION_SCOPES.map((item) => item.label).join(", ");

  return (
    <div id={id} className="scope-note" aria-live="polite">
      {!stored ? (
        <p>Sin alcance guardado. Las opciones son: {knownLabels}.</p>
      ) : scope ? (
        <p>{scope.description}</p>
      ) : (
        <p>
          Valor histórico «{stored}». Se conserva al guardar. El catálogo actual no define una descripción ni una estimación base para este texto.
        </p>
      )}
      {!hideEstimate && scope?.estimate ? (
        <p>
          Estimación base para 1 recurso QC: {scope.estimate.label}. Es una referencia de horas-persona definida por QC.
          {resources > 1
            ? ` Hay ${resources} recursos asignados; esta referencia no se convierte en tiempo calendario.`
            : " El tiempo calendario se ve aparte, con la ventana y los recursos de la Release."}
          {" "}El esfuerzo de los casos de CaseForge se calcula con su fórmula propia. No se suma a los casos de la matriz.
        </p>
      ) : !hideEstimate && stored === "N/A" ? (
        <p>No hay esfuerzo estimado de validación.</p>
      ) : null}
      {stored === "N/A" ? (
        <p className="muted">No se incorporarán casos de la matriz QC por este concepto.</p>
      ) : hideEstimate ? null : matrixCaseCount == null ? (
        <p className="muted">
          Los casos de la matriz se cuentan cuando hay una versión publicada para el dispositivo de la Release.
        </p>
      ) : matrixNote ? (
        <p>{matrixNote}</p>
      ) : null}
    </div>
  );
}
