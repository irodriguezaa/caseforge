"""FASE 8 FIX 3: the validator rejects; the writer does not patch the LLM answer."""

from __future__ import annotations

from app.schemas.case_generation import CandidateStep, GeneratedCaseCandidate, GenerationStats
from app.services.gherkin_coverage import candidates_from_jira_artifacts
from app.services.scenario_cases import lift_technical
from app.services.scenario_llm import validate_llm_case


def _artifacts(stories: list[tuple[str, str, str, str]]) -> list[dict]:
    by_epic: dict[str, list[dict]] = {}
    for epic, story, summary, description in stories:
        by_epic.setdefault(epic, []).append(
            {
                "key": story,
                "issuetype": "Technical Story",
                "summary": summary,
                "description": description,
                "acceptance_criteria": "",
            }
        )
    return [
        {"key": epic, "issuetype": "Technical Epic", "children": children}
        for epic, children in by_epic.items()
    ]


def _cases(description: str, summary: str = "Feature ejemplo"):
    stats = GenerationStats()
    cases = candidates_from_jira_artifacts(
        _artifacts([("EPC-1", "ST-1", summary, description)]),
        "rn.pdf",
        [],
        lambda *_a: None,
        stats=stats,
    )
    return cases, stats


def _llm(**overrides) -> GeneratedCaseCandidate:
    base = dict(
        name="Confirmar el pago",
        description="Confirmar el pago",
        evidence="When el usuario selecciona Confirmar",
        justification="test",
        precondition="El socio tiene una reserva activa.",
        steps=[
            CandidateStep(
                step_number=1,
                action='Seleccionar "Confirmar"',
                expected_result='Se muestra "Pago registrado".',
            )
        ],
    )
    base.update(overrides)
    return GeneratedCaseCandidate(**base)


def test_r2_lift_keeps_the_closing_quote_and_period() -> None:
    text = 'Hacer clic en el botón "Siguiente".'
    cleaned, idents = lift_technical(text)
    assert cleaned == text
    assert idents == []


def test_r3_validator_rejects_a_repeated_action_and_late_navigation() -> None:
    repeated = _llm(
        steps=[
            CandidateStep(step_number=1, action="Seleccionar el título", expected_result="Se muestra la ficha."),
            CandidateStep(step_number=2, action="Seleccionar el título", expected_result="Se muestra el estado."),
        ]
    )
    assert any("repite" in reason for reason in validate_llm_case(repeated, "When el usuario selecciona el título", []))
    late = _llm(
        steps=[
            CandidateStep(step_number=1, action="Seleccionar el título reservado", expected_result="Se muestra la ficha del título."),
            CandidateStep(step_number=2, action="Abrir el menú principal", expected_result="Se muestra el menú principal con sus opciones."),
        ]
    )
    reasons = validate_llm_case(
        late,
        "When el usuario selecciona el título",
        [],
        background="Given el usuario abre el menú principal",
    )
    assert any("navegación" in reason for reason in reasons)


def test_r4_validator_rejects_filler_results() -> None:
    echo = _llm(
        steps=[
            CandidateStep(step_number=1, action="Seleccionar continuar", expected_result="Se muestra el continuar."),
        ]
    )
    bare = _llm(
        steps=[
            CandidateStep(step_number=1, action="Seleccionar continuar", expected_result="Se muestra un evento."),
        ]
    )
    generic = _llm(
        steps=[
            CandidateStep(
                step_number=1,
                action="Seleccionar continuar",
                expected_result="Se muestra el resultado de: Seleccionar continuar.",
            ),
        ]
    )
    assert any("repite" in reason for reason in validate_llm_case(echo, "When el usuario selecciona continuar", []))
    assert any("relleno" in reason for reason in validate_llm_case(bare, "When el usuario selecciona continuar", []))
    assert any("resultado de" in reason for reason in validate_llm_case(generic, "When el usuario selecciona continuar", []))


def test_r5_validator_rejects_numbered_and_cut_titles() -> None:
    numbered = _llm(name="Solicitar PIN — 02: seguridad del perfil")
    cut = _llm(name="Solicitar PIN — seguridad del")
    unique = _llm(name="Solicitar PIN — perfil adulto")
    assert any("numeración" in reason for reason in validate_llm_case(numbered, "When el usuario solicita el PIN", []))
    assert any("cortado" in reason for reason in validate_llm_case(cut, "When el usuario solicita el PIN", [], repeated_title=True))
    assert any("no se repite" in reason for reason in validate_llm_case(unique, "When el usuario solicita el PIN", []))


def test_r6_system_when_without_visible_behavior_is_not_a_case() -> None:
    cases, stats = _cases(
        """
Feature: Arranque
  Scenario: Inicializar métricas
    When el sistema procesa el arranque en frío
    Then se emite un evento de inicio
"""
    )
    assert not any(row.steps for row in cases)
    assert any(row.get("estado") == "verificación técnica" for row in stats.scenario_ledger)


def test_r6_validator_rejects_a_technical_precondition() -> None:
    technical = _llm(precondition="El SDK está inicializado y el contexto técnico está listo.")
    reasons = validate_llm_case(technical, "When el usuario selecciona Confirmar", [])
    assert any("precondición" in reason for reason in reasons)


def test_r3_several_background_steps_compact_into_one_path() -> None:
    cases, _stats = _cases(
        """
Feature: Catálogo
  Background:
    Given el usuario abre inicio
    And el usuario ingresa al catálogo
    And el usuario selecciona reservas
  Scenario: Ver la ficha
    When el usuario selecciona el título
    Then se muestra la ficha
"""
    )
    case = next(row for row in cases if row.steps)
    assert " > " in (case.steps[0].action or "")
    assert case.steps[0].action.lower().startswith("ingresar a")
