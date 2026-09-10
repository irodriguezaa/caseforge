"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { StatusBadge } from "@/app/components/StatusBadge";
import { api, ApiRequestError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { TestCase, TestCaseWithSteps, TestStep } from "@/lib/types";
import { formatRnSourceType } from "@/lib/types";

const emptyStepForm = { step_number: 1, test_step: "", expected_result: "" };

export default function TestCaseDetailPage(): React.ReactElement {
  const params = useParams<{ id: string }>();
  const testCaseId = Number(params.id);
  const { canExecuteCases } = useAuth();

  const [testCase, setTestCase] = useState<TestCaseWithSteps | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [stepForm, setStepForm] = useState(emptyStepForm);
  const [submittingStep, setSubmittingStep] = useState(false);

  const load = (): void => {
    setLoadError(null);
    api
      .getTestCase(testCaseId)
      .then((data) => {
        setTestCase(data);
        setStepForm({ ...emptyStepForm, step_number: data.steps.length + 1 });
      })
      .catch((err: unknown) => setLoadError(err instanceof Error ? err.message : "Error"));
  };

  useEffect(load, [testCaseId]);

  const handleStatusChange = async (status: TestCase["status"]): Promise<void> => {
    setActionError(null);
    try {
      const updated = await api.updateTestCase(testCaseId, { status });
      setTestCase(updated);
    } catch (err) {
      setActionError(err instanceof ApiRequestError ? err.message : "No se pudo actualizar el estado.");
    }
  };

  const handleAddStep = async (event: React.FormEvent): Promise<void> => {
    event.preventDefault();
    setSubmittingStep(true);
    setActionError(null);
    try {
      await api.addStep(testCaseId, stepForm);
      load();
    } catch (err) {
      setActionError(err instanceof ApiRequestError ? err.message : "No se pudo agregar el step.");
    } finally {
      setSubmittingStep(false);
    }
  };

  const handleDeleteStep = async (stepId: number): Promise<void> => {
    setActionError(null);
    try {
      await api.deleteStep(stepId);
      load();
    } catch (err) {
      setActionError(err instanceof ApiRequestError ? err.message : "No se pudo eliminar el step.");
    }
  };

  const handleMoveStep = async (steps: TestStep[], index: number, direction: -1 | 1): Promise<void> => {
    const targetIndex = index + direction;
    if (targetIndex < 0 || targetIndex >= steps.length) return;
    setActionError(null);
    try {
      const a = steps[index];
      const b = steps[targetIndex];
      await api.reorderSteps(testCaseId, [
        { id: a.id, step_number: b.step_number },
        { id: b.id, step_number: a.step_number },
      ]);
      load();
    } catch (err) {
      setActionError(err instanceof ApiRequestError ? err.message : "No se pudo reordenar.");
    }
  };

  if (loadError) {
    return (
      <div className="page">
        <p className="error-text">{loadError}</p>
      </div>
    );
  }

  if (!testCase) {
    return (
      <div className="page">
        <p className="muted">Cargando…</p>
      </div>
    );
  }

  return (
    <div className="page">
      <p className="eyebrow">Test Case</p>
      <h1>{testCase.test_case_id}</h1>
      <p className="subtitle">
        {testCase.test_case_name}
      </p>
      <p>
        <StatusBadge status={testCase.priority} /> <StatusBadge status={testCase.test_type} />{" "}
        {testCase.source_type ? <StatusBadge status={formatRnSourceType(testCase.source_type)} /> : null}{" "}
        <StatusBadge status={testCase.status} />
      </p>
      {testCase.description && <p>{testCase.description}</p>}
      <div className="muted" style={{ fontSize: "13px", marginTop: "8px" }}>
        {testCase.complexity ? (
          <span>
            Complejidad IA: <strong>{testCase.complexity}</strong>
            {testCase.confidence ? ` · Confianza: ${testCase.confidence}` : ""}
          </span>
        ) : null}
      </div>
      {testCase.requires_condition ? <p className="muted">Requiere condición especial.</p> : null}
      {testCase.test_data ? (
        <div className="card" style={{ marginTop: "12px" }}>
          <h2>Datos de Prueba</h2>
          <p style={{ whiteSpace: "pre-wrap", margin: 0 }}>{testCase.test_data}</p>
        </div>
      ) : null}
      {(testCase.technical_epic || testCase.technical_story || testCase.scenario_origin) && (
        <div className="card" style={{ marginTop: "12px" }}>
          <h2>Trazabilidad</h2>
          {testCase.technical_epic ? <p>Technical Epic: {testCase.technical_epic}</p> : null}
          {testCase.technical_story ? <p>Technical Story: {testCase.technical_story}</p> : null}
          {testCase.scenario_origin ? (
            <p style={{ whiteSpace: "pre-wrap" }}>Scenario / origen: {testCase.scenario_origin}</p>
          ) : null}
          {testCase.justification ? <p style={{ whiteSpace: "pre-wrap" }}>{testCase.justification}</p> : null}
        </div>
      )}

      {actionError && <p className="error-text">{actionError}</p>}

      {canExecuteCases && (
      <div className="card">
        <h2>Cambiar estado de ejecución</h2>
        <div className="form-actions">
          {(["UNEXECUTED", "PASS", "FAIL", "BLOCKED", "N_A"] as const).map((status) => (
            <button
              key={status}
              type="button"
              className={status === testCase.status ? "" : "secondary"}
              onClick={() => handleStatusChange(status)}
            >
              {status.replace("_", " ")}
            </button>
          ))}
        </div>
      </div>
      )}

      <div className="section-header">
        <h2>Steps</h2>
      </div>

      <ul className="steps-list">
        {testCase.steps.map((step, index) => (
          <li key={step.id} className="step-row">
            <span className="step-number">{step.step_number}</span>
            <div>
              <strong>{step.test_step}</strong>
              <p className="muted" style={{ margin: ".35rem 0 0" }}>
                Esperado: {step.expected_result}
              </p>
            </div>
            <div className="step-actions">
              {canExecuteCases && (
              <>
              <button
                type="button"
                className="secondary"
                disabled={index === 0}
                onClick={() => handleMoveStep(testCase.steps, index, -1)}
              >
                ↑
              </button>
              <button
                type="button"
                className="secondary"
                disabled={index === testCase.steps.length - 1}
                onClick={() => handleMoveStep(testCase.steps, index, 1)}
              >
                ↓
              </button>
              <button type="button" className="danger" onClick={() => handleDeleteStep(step.id)}>
                Eliminar
              </button>
              </>
              )}
            </div>
          </li>
        ))}
        {testCase.steps.length === 0 && <p className="muted">Sin steps todavía.</p>}
      </ul>

      {canExecuteCases && (
      <div className="card" style={{ marginTop: "1.5rem" }}>
        <h2>Agregar Step</h2>
        <form onSubmit={handleAddStep}>
          <div className="form-grid">
            <div className="form-field">
              <label htmlFor="step_number">#</label>
              <input
                id="step_number"
                type="number"
                min={1}
                required
                value={stepForm.step_number}
                onChange={(e) => setStepForm({ ...stepForm, step_number: Number(e.target.value) })}
              />
            </div>
            <div className="form-field full">
              <label htmlFor="test_step">Test Step</label>
              <textarea
                id="test_step"
                required
                value={stepForm.test_step}
                onChange={(e) => setStepForm({ ...stepForm, test_step: e.target.value })}
              />
            </div>
            <div className="form-field full">
              <label htmlFor="expected_result">Resultado esperado</label>
              <textarea
                id="expected_result"
                required
                value={stepForm.expected_result}
                onChange={(e) => setStepForm({ ...stepForm, expected_result: e.target.value })}
              />
            </div>
          </div>
          <div className="form-actions">
            <button type="submit" disabled={submittingStep}>
              {submittingStep ? "Agregando…" : "Agregar Step"}
            </button>
          </div>
        </form>
      </div>
      )}

      <p style={{ marginTop: "1.5rem" }}>
        <Link href={`/releases/${testCase.release_id}`} className="back-link">
          ← Volver a la Release
        </Link>
      </p>
    </div>
  );
}
