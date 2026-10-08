"""B = condition, A = user action, C = observable. Never mix B into A."""

from app.schemas.case_generation import CandidateStep, CoverageUnit, GeneratedCaseCandidate
from app.services.ai_case_engine import _candidate_from_functionality_ticket
from app.services.executability import (
    STABLE_GENERIC_STEP,
    apply_executability_gate,
    bound_user_action,
    build_test_intent,
    is_generic_action,
    step_smuggles_condition,
)
from app.services.gherkin_coverage import build_coverage_inventory, candidates_from_jira_artifacts
from app.services.qc_candidate_rules import apply_qc_rules, rewrite_step_language
from tests.test_scenario_classifier import _artifacts


def test_test_intent_is_semantic_not_key_hardcoded() -> None:
    empty = build_test_intent("La llave se encuentra vacía")
    missing = build_test_intent("No se logra obtener una llave")
    assert empty != missing
    assert "vacía" in empty.lower()
    assert "no se logra" in missing.lower()


def test_bound_action_is_stable_generic_without_condition() -> None:
    a = bound_user_action("No se logra obtener una llave")
    b = bound_user_action("La llave se encuentra vacía")
    assert a == b == STABLE_GENERIC_STEP
    assert "cuando" not in a.lower()


def test_when_of_user_is_kept_as_step() -> None:
    cases = candidates_from_jira_artifacts(_artifacts(), "rn.pdf", [], lambda *_a: None)
    ticket = next(item for item in cases if "ticket actualizado" in item.name.lower())
    assert any("visualiza la pantalla de ticket" in step.action.lower() for step in ticket.steps)
    assert not any(step_smuggles_condition(step.action) for step in ticket.steps)


def test_when_technical_puts_condition_in_precondition_not_step() -> None:
    internal = CandidateStep(
        step_number=1,
        action="El sistema consulta el servicio de metadata",
        expected_result="No se muestra un error visible para el usuario",
    )
    first = rewrite_step_language(internal, "No se logra obtener una llave")
    second = rewrite_step_language(internal, "La llave se encuentra vacía")
    assert first.action == second.action == STABLE_GENERIC_STEP
    assert "cuando" not in first.action.lower()
    gated = apply_executability_gate(
        apply_qc_rules(
            [
                GeneratedCaseCandidate(
                    name="No se logra obtener una llave",
                    description="x",
                    evidence="x",
                    justification="x",
                    covers=["COV-010"],
                    steps=[internal],
                ),
                GeneratedCaseCandidate(
                    name="La llave se encuentra vacía",
                    description="x",
                    evidence="x",
                    justification="x",
                    covers=["COV-011"],
                    steps=[
                        CandidateStep(
                            step_number=1,
                            action="El sistema consulta el servicio de metadata",
                            expected_result="No se muestra un error visible para el usuario",
                        )
                    ],
                ),
            ]
        )
    )
    assert len(gated) == 2
    for row in gated:
        assert row.steps[0].action == STABLE_GENERIC_STEP
        assert "cuando" not in row.steps[0].action.lower()
        blob = f"{row.precondition} {row.test_data} {row.name}".lower()
        assert "llave" in blob or "vacía" in blob or "no se logra" in blob


def test_when_technical_plus_recoverable_user_action() -> None:
    unit = CoverageUnit(
        coverage_id="COV-001",
        role="A",
        behavior="Contenido no disponible",
        scenario="Contenido no disponible",
        test_intent=build_test_intent("Contenido no disponible"),
        evidence="",
        body=(
            "Given el contenido no está disponible para el perfil\n"
            "When el usuario selecciona el título\n"
            "Then se muestra el estado de no disponible y no se inicia la reproducción\n"
        ),
        observable_then=["se muestra el estado de no disponible y no se inicia la reproducción"],
        special_condition="el contenido no está disponible para el perfil",
    )
    candidate = GeneratedCaseCandidate(
        name="Contenido no disponible",
        description="UX",
        evidence=unit.evidence,
        justification="LLM",
        covers=["COV-001"],
        steps=[
            CandidateStep(
                step_number=1,
                action="El usuario recorre la experiencia cuando contenido no disponible.",
                expected_result="Se muestra el comportamiento esperado.",
            )
        ],
        generation_origin="llm",
    )
    gated = apply_executability_gate([candidate], [unit])[0]
    assert "selecciona el título" in gated.steps[0].action.lower()
    assert "cuando" not in gated.steps[0].action.lower()
    assert "no está disponible" in (gated.precondition or "").lower()
    assert "no disponible" in gated.steps[0].expected_result.lower()


def test_when_of_state_is_not_used_as_step() -> None:
    cases = candidates_from_jira_artifacts(_artifacts(), "rn.pdf", [], lambda *_a: None)
    cuenta = next(item for item in cases if "cuenta no disponible" in (item.name + item.evidence).lower())
    for step in cuenta.steps:
        assert "se muestra la leyenda" not in step.action.lower()
        assert not step_smuggles_condition(step.action)
    blob = " ".join(step.expected_result.lower() for step in cuenta.steps)
    assert "leyenda" in blob or "renderizado" in blob or "layout" in blob
    assert "null" in (cuenta.precondition or "").lower() or "cuenta" in (cuenta.precondition or "").lower()


def test_then_and_goes_to_expected_not_precondition() -> None:
    cases = candidates_from_jira_artifacts(_artifacts(), "rn.pdf", [], lambda *_a: None)
    info = next(
        item
        for item in cases
        if "texto informativo" in item.name.lower() and "longitud" not in item.name.lower()
    )
    assert "usuario@dominio.com" not in (info.precondition or "").lower()
    joined_exp = " ".join(step.expected_result for step in info.steps).lower()
    assert "paypal" in joined_exp or "texto" in joined_exp
    assert any("transacciona" in step.action.lower() for step in info.steps)


def test_sibling_key_conditions_are_not_copied_to_other_cases() -> None:
    cases = candidates_from_jira_artifacts(_artifacts(), "rn.pdf", [], lambda *_a: None)
    ticket = next(item for item in cases if "ticket actualizado" in item.name.lower())
    blob = f"{ticket.precondition} {ticket.test_data}".lower()
    assert "apa/metadata" not in blob
    assert "llave se encuentra vacía" not in blob
    assert "no se logra obtener" not in blob


def test_cuando_condition_in_step_is_reconstructed() -> None:
    candidate = GeneratedCaseCandidate(
        name="La llave se encuentra vacía",
        description="x",
        evidence="x",
        justification="x",
        steps=[
            CandidateStep(
                step_number=1,
                action="El usuario recorre la experiencia cuando la llave se encuentra vacía.",
                expected_result="Se muestra el comportamiento esperado.",
            )
        ],
    )
    gated = apply_executability_gate([candidate])[0]
    assert gated.steps[0].action == STABLE_GENERIC_STEP
    assert "cuando" not in gated.steps[0].action.lower()
    assert "vacía" in (gated.precondition or "").lower()
    assert "vacía" in gated.steps[0].expected_result.lower()


def test_last_resort_does_not_invent_a_user_action() -> None:
    row = _candidate_from_functionality_ticket(
        "ADTCL-2787",
        "ADTCL-2787: Migración de usuario a la marca Claro tv+",
        "adt.pdf",
        [],
    )
    assert row is not None
    gated = apply_executability_gate(apply_qc_rules([row]))[0]
    assert gated.steps[0].action == STABLE_GENERIC_STEP
    assert "recorre la experiencia de" not in gated.steps[0].action.lower()
    assert "validación básica" in (gated.precondition or "").lower() or "validación básica" in gated.steps[
        0
    ].expected_result.lower()


def test_inventory_volume_and_roles_unchanged() -> None:
    units = build_coverage_inventory(_artifacts(), "rn.pdf")
    scenarios = {unit.scenario for unit in units}
    assert "No se logra obtener una llave" in scenarios
    assert "La llave se encuentra vacía" in scenarios
    assert len(units) == 8
    assert all(unit.role in {"A", "G"} for unit in units)


def test_length_exceeded_condition_is_not_the_step() -> None:
    cases = candidates_from_jira_artifacts(_artifacts(), "rn.pdf", [], lambda *_a: None)
    long_text = next(item for item in cases if "longitud" in item.name.lower())
    assert all("supera el límite" not in step.action.lower() for step in long_text.steps)
    expected_blob = " ".join(step.expected_result for step in long_text.steps)
    assert "..." in expected_blob or "límite" in expected_blob.lower()
    assert long_text.steps[0].action == STABLE_GENERIC_STEP or "usuario" in long_text.steps[0].action.lower()
