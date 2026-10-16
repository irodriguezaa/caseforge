"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { QcMatrixPreview } from "@/lib/types";
import { validationScopeByLabel } from "@/lib/validationScope";

type MatrixImpact = { caseCount: number; note: string; estimateInSection: boolean };

type MatrixScopeEditorProps = {
  platform: string;
  cluster?: string | null;
  validationType: string;
  rawAnalysis?: Record<string, unknown> | null;
  releaseId?: number | null;
  touchedModules: string[] | null;
  templateValues: Record<string, string> | null;
  qcResources?: number | null;
  readOnly?: boolean;
  /** editor: Paso 3. summary: tarjeta de solo lectura en el detalle de la Release. */
  variant?: "editor" | "summary";
  onTouchedModules: (modules: string[] | null) => void;
  onTemplateValues: (values: Record<string, string>) => void;
  onPreview: (preview: MatrixImpact | null) => void;
};

function quantity(count: number, singular: string, plural: string): string {
  return `${count} ${count === 1 ? singular : plural}`;
}

function caseLabel(count: number): string {
  return quantity(count, "caso", "casos");
}

export function MatrixScopeEditor({
  platform,
  cluster,
  validationType,
  rawAnalysis,
  releaseId,
  touchedModules,
  templateValues,
  qcResources,
  readOnly = false,
  variant = "editor",
  onTouchedModules,
  onPreview,
}: MatrixScopeEditorProps): React.ReactElement | null {
  const [preview, setPreview] = useState<QcMatrixPreview | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [modulesOpen, setModulesOpen] = useState(false);
  const onPreviewRef = useRef(onPreview);
  onPreviewRef.current = onPreview;

  useEffect(() => {
    if (!platform && !releaseId) {
      setPreview(null);
      onPreviewRef.current(null);
      return;
    }
    let cancelled = false;
    api
      .previewQcMatrix({
        platform,
        validation_type: validationType,
        touched_modules: touchedModules,
        template_values: templateValues,
        raw_analysis: rawAnalysis ?? null,
        release_id: releaseId ?? null,
      })
      .then((data) => {
        if (cancelled) return;
        setPreview(data);
        onPreviewRef.current({
          caseCount: data.case_count,
          note: data.note,
          estimateInSection: data.validation_type !== "N/A" && Boolean(data.matrix_code || data.note),
        });
      })
      .catch(() => {
        if (cancelled) return;
        setPreview(null);
        onPreviewRef.current(null);
      });
    return () => {
      cancelled = true;
    };
  }, [platform, validationType, rawAnalysis, releaseId, touchedModules, templateValues]);

  useEffect(() => {
    setModulesOpen(false);
  }, [validationType, releaseId]);

  const byKey = useMemo(() => {
    const map = new Map<string, QcMatrixPreview["modules"][number]>();
    for (const module of preview?.modules ?? []) map.set(module.module_key, module);
    return map;
  }, [preview]);

  if (!preview || validationType === "N/A" || preview.validation_type === "N/A") {
    return null;
  }

  const showSelector = preview.show_module_selector === true && preview.modules.length > 0;
  const evidence = new Map((preview.suggestions ?? []).map((item) => [item.module_key, item.matched_words]));
  const scope = validationScopeByLabel(validationType);
  const resources = Math.max(1, Number(qcResources) || 1);
  const noSuggestion = preview.suggested_modules.length === 0 && preview.touched_modules.length === 0;
  const relatedNames = preview.related_modules
    .map((key) => byKey.get(key)?.name)
    .filter((name): name is string => Boolean(name));

  const needle = query.trim().toLocaleLowerCase("es");
  const groups = new Map<string, QcMatrixPreview["modules"]>();
  for (const module of preview.modules) {
    if (preview.touched_modules.includes(module.module_key)) continue;
    if (needle && !`${module.group_name} ${module.name}`.toLocaleLowerCase("es").includes(needle)) continue;
    const group = module.group_name || "Sin grupo";
    const rows = groups.get(group) ?? [];
    rows.push(module);
    groups.set(group, rows);
  }

  const removeModule = (moduleKey: string): void => {
    onTouchedModules(preview.touched_modules.filter((key) => key !== moduleKey));
  };
  const addModule = (moduleKey: string): void => {
    onTouchedModules([...preview.touched_modules, moduleKey]);
  };

  if (variant === "summary") {
    const selected = new Map<string, number>();
    for (const row of preview.cases ?? []) {
      const key = row.module_key;
      if (!key) continue;
      selected.set(key, (selected.get(key) ?? 0) + 1);
    }
    const moduleCount = selected.size;
    const scopeName = validationType.trim() || preview.validation_type;
    const hours = scope?.estimate?.label.replace(/^Aproximadamente\s+/i, "") ?? "";
    const listed = [...selected.entries()].map(([key, count]) => ({
      key,
      count,
      name: byKey.get(key)?.name ?? key,
    }));
    return (
      <div className="scope-note" style={{ marginTop: "0.6rem" }}>
        {preview.matrix_code ? (
          <>
            <p>
              Matriz {preview.matrix_code} {preview.matrix_version} ·{" "}
              {preview.platform === "BE" ? "todos los dispositivos OTT/IPTV" : preview.platform} · Cluster:{" "}
              {cluster?.trim() || "—"}
            </p>
            <p>
              {scopeName}: {caseLabel(preview.case_count)} de {quantity(moduleCount, "módulo", "módulos")}
            </p>
            {hours ? <p>Estimación base (1 recurso QC): {hours}</p> : null}
            {listed.length > 0 ? (
              <>
                <button type="button" className="matrix-summary-toggle" onClick={() => setModulesOpen((open) => !open)}>
                  {modulesOpen ? "Ocultar módulos" : "Ver módulos"}
                </button>
                {modulesOpen ? (
                  <>
                    <div className="matrix-chips">
                      {listed.map((module) => (
                        <span key={module.key} className="matrix-chip">
                          {module.name} · {caseLabel(module.count)}
                        </span>
                      ))}
                    </div>
                    {validationType === "Regresivo" && relatedNames.length > 0 ? (
                      <p className="matrix-related">Se incluyen por relación: {relatedNames.join(", ")}.</p>
                    ) : null}
                    {validationType === "No Afectación" && relatedNames.length > 0 ? (
                      <p className="matrix-related">Relacionados con el cambio: {relatedNames.join(", ")}.</p>
                    ) : null}
                  </>
                ) : null}
              </>
            ) : null}
          </>
        ) : preview.note ? (
          <p>{preview.note}</p>
        ) : null}
      </div>
    );
  }

  return (
    <div className="scope-note" style={{ marginTop: "0.6rem" }}>
      {preview.matrix_code ? (
        <p className="matrix-context">
          Matriz {preview.matrix_code} {preview.matrix_version} ·{" "}
          {preview.platform === "BE" ? "todos los dispositivos OTT/IPTV" : `Dispositivo: ${preview.platform}`} · Cluster:{" "}
          {cluster?.trim() || "—"}.
        </p>
      ) : preview.note ? (
        <p>{preview.note}</p>
      ) : null}

      {showSelector ? (
        <>
          {noSuggestion ? (
            <p>No se detectaron módulos en el RN. Agrega los módulos que toca el cambio.</p>
          ) : preview.touched_modules.length > 0 ? (
            <div className="matrix-chips">
              {preview.touched_modules.map((key) => {
                const module = byKey.get(key);
                const words = evidence.get(key) ?? [];
                const count = module?.device_case_count ?? 0;
                return (
                  <span key={key} className="matrix-chip" title={words.length ? `Sugerido por: ${words.join(", ")}` : undefined}>
                    {module?.name ?? key} · {caseLabel(count)}
                    {readOnly ? null : (
                      <button type="button" aria-label={`Quitar ${module?.name ?? key}`} onClick={() => removeModule(key)}>
                        ✕
                      </button>
                    )}
                  </span>
                );
              })}
            </div>
          ) : null}
          {readOnly ? null : (
            <div className="matrix-add">
              <button type="button" onClick={() => setPickerOpen((open) => !open)}>
                + Agregar módulo
              </button>
              {pickerOpen ? (
                <div className="matrix-picker">
                  <input
                    value={query}
                    placeholder="Buscar módulo"
                    aria-label="Buscar módulo"
                    onChange={(event) => setQuery(event.target.value)}
                  />
                  {[...groups.entries()].map(([group, modules]) => (
                    <div key={group} className="matrix-picker-group">
                      <b>{group}</b>
                      {modules.map((module) => {
                        const count = module.device_case_count ?? 0;
                        return (
                          <button
                            key={module.module_key}
                            type="button"
                            className="matrix-picker-option"
                            disabled={count === 0}
                            title={count === 0 ? "Sin casos para este dispositivo" : undefined}
                            onClick={() => addModule(module.module_key)}
                          >
                            <span>{module.name}</span>
                            <span>{caseLabel(count)}</span>
                          </button>
                        );
                      })}
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          )}
          {validationType === "Regresivo" && relatedNames.length > 0 ? (
            <p className="matrix-related">Se incluyen por relación: {relatedNames.join(", ")}.</p>
          ) : null}
          {validationType === "No Afectación" && relatedNames.length > 0 ? (
            <p className="matrix-related">Relacionados con el cambio: {relatedNames.join(", ")}.</p>
          ) : null}
        </>
      ) : null}

      {preview.impact_summary ? <p>{preview.impact_summary}</p> : null}
      {scope?.estimate ? (
        <p>
          Estimación base para 1 recurso QC: {scope.estimate.label}. Se suma al esfuerzo de los casos del RN; en un rango entra el tope. Los casos de la matriz no entran en esa fórmula.
          {resources > 1 ? ` Hay ${resources} recursos asignados; esta referencia no se convierte en tiempo calendario.` : ""}
        </p>
      ) : null}
    </div>
  );
}
