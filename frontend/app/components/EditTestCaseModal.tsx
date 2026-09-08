"use client";

import { useEffect, useState } from "react";
import { api, ApiRequestError } from "@/lib/api";
import type { TestCase, TestCaseStatus, TestCaseWithSteps } from "@/lib/types";

interface DraftStep {
  step_number: number;
  test_step: string;
  expected_result: string;
}

interface EditTestCaseModalProps {
  releaseId: number;
  testCase: TestCase;
  onClose: () => void;
  onSaved: (updated: TestCaseWithSteps) => void;
}

export function EditTestCaseModal({
  releaseId,
  testCase,
  onClose,
  onSaved,
}: EditTestCaseModalProps): React.ReactElement {
  const [name, setName] = useState(testCase.test_case_name);
  const [description, setDescription] = useState(testCase.description ?? "");
  const [priority, setPriority] = useState(testCase.priority);
  const [status, setStatus] = useState<TestCaseStatus>(testCase.status);
  const [steps, setSteps] = useState<DraftStep[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .getTestCase(testCase.id)
      .then((full) => {
        if (cancelled) return;
        setName(full.test_case_name);
        setDescription(full.description ?? "");
        setPriority(full.priority);
        setStatus(full.status);
        setSteps(
          full.steps.length
            ? full.steps.map((step) => ({
                step_number: step.step_number,
                test_step: step.test_step,
                expected_result: step.expected_result,
              }))
            : [{ step_number: 1, test_step: "", expected_result: "" }],
        );
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "No se pudo cargar el Test Case.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [testCase.id]);

  const updateStep = (index: number, patch: Partial<DraftStep>): void => {
    setSteps((current) => current.map((step, i) => (i === index ? { ...step, ...patch } : step)));
  };

  const addStep = (): void => {
    setSteps((current) => [
      ...current,
      { step_number: current.length + 1, test_step: "", expected_result: "" },
    ]);
  };

  const removeStep = (index: number): void => {
    setSteps((current) =>
      current
        .filter((_, i) => i !== index)
        .map((step, i) => ({ ...step, step_number: i + 1 })),
    );
  };

  const handleSave = async (event: React.FormEvent): Promise<void> => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    const cleaned = steps
      .filter((step) => step.test_step.trim() || step.expected_result.trim())
      .map((step, index) => ({
        step_number: index + 1,
        test_step: step.test_step.trim(),
        expected_result: step.expected_result.trim() || "—",
      }));
    if (cleaned.some((step) => !step.test_step)) {
      setError("Cada Test Step debe tener una acción.");
      setSaving(false);
      return;
    }
    try {
      const updated = await api.updateTestCase(
        testCase.id,
        {
          test_case_name: name.trim(),
          description: description.trim() || null,
          priority,
          status,
          steps: cleaned,
        },
        releaseId,
      );
      onSaved(updated);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "No se pudo guardar el Test Case.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="modal-panel"
        role="dialog"
        aria-labelledby="edit-test-case-title"
        onClick={(event) => event.stopPropagation()}
      >
        <h2 id="edit-test-case-title">Editar Test Case</h2>
        <p className="muted" style={{ fontSize: "12.5px", marginTop: "-6px" }}>
          {testCase.test_case_id} · se actualiza el mismo caso, sin duplicar ni regenerar.
        </p>
        {loading ? (
          <p className="muted">Cargando…</p>
        ) : (
          <form onSubmit={(event) => void handleSave(event)}>
            <div className="form-grid">
              <div className="form-field full">
                <label htmlFor="edit-tc-name">Nombre / Título</label>
                <input
                  id="edit-tc-name"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </div>
              <div className="form-field full">
                <label htmlFor="edit-tc-description">Descripción</label>
                <textarea
                  id="edit-tc-description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </div>
              <div className="form-field">
                <label htmlFor="edit-tc-priority">Prioridad</label>
                <select
                  id="edit-tc-priority"
                  value={priority}
                  onChange={(e) => setPriority(e.target.value as TestCase["priority"])}
                >
                  <option value="BLOCKER">BLOCKER</option>
                  <option value="CRITICAL">CRITICAL</option>
                </select>
              </div>
              <div className="form-field">
                <label htmlFor="edit-tc-status">Estado</label>
                <select
                  id="edit-tc-status"
                  value={status}
                  onChange={(e) => setStatus(e.target.value as TestCaseStatus)}
                >
                  <option value="UNEXECUTED">UNEXECUTED</option>
                  <option value="PASS">PASS</option>
                  <option value="FAIL">FAIL</option>
                  <option value="BLOCKED">BLOCKED</option>
                  <option value="N_A">N/A</option>
                </select>
              </div>
            </div>
            <div style={{ marginTop: "1rem" }}>
              <div className="section-header" style={{ marginBottom: "8px" }}>
                <h2 style={{ margin: 0 }}>Test Steps</h2>
                <button type="button" className="secondary" onClick={addStep}>
                  Agregar step
                </button>
              </div>
              {steps.map((step, index) => (
                <div key={index} className="form-grid" style={{ marginBottom: "10px" }}>
                  <div className="form-field">
                    <label>Paso {step.step_number}</label>
                    <textarea
                      required
                      placeholder="Acción"
                      value={step.test_step}
                      onChange={(e) => updateStep(index, { test_step: e.target.value })}
                    />
                  </div>
                  <div className="form-field">
                    <label>Resultado esperado</label>
                    <textarea
                      placeholder="Resultado esperado"
                      value={step.expected_result}
                      onChange={(e) => updateStep(index, { expected_result: e.target.value })}
                    />
                  </div>
                  <div className="form-field" style={{ justifyContent: "flex-end" }}>
                    <button type="button" className="danger" onClick={() => removeStep(index)}>
                      Quitar
                    </button>
                  </div>
                </div>
              ))}
            </div>
            {error && <p className="error-text">{error}</p>}
            <div className="form-actions">
              <button type="submit" disabled={saving}>
                {saving ? "Guardando…" : "Guardar"}
              </button>
              <button type="button" className="secondary" onClick={onClose} disabled={saving}>
                Cancelar
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
