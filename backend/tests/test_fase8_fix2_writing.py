"""FASE 8 FIX 2: writing rules X4–X8. Synthetic Gherkin only."""

from __future__ import annotations

from app.schemas.case_generation import CandidateStep, GeneratedCaseCandidate, GenerationStats
from app.services.gherkin_coverage import candidates_from_jira_artifacts
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


def test_x4_state_then_has_no_quotes_and_missing_data_is_defined_by_qc() -> None:
    cases, _stats = _cases(
        """
Feature: Acceso
  Scenario: Ingresar PIN
    When el usuario ingresa el PIN
    Then el PIN fue ingresado correctamente
"""
    )
    case = next(row for row in cases if row.steps)
    blob = " ".join(step.expected_result or "" for step in case.steps)
    assert "Se muestra el mensaje" not in blob
    assert '"' not in blob and "“" not in blob
    assert "PIN fue ingresado correctamente" in blob
    assert "Definir por QC:" in (case.test_data or "")
    assert "PIN" in (case.test_data or "")


def test_x4_validator_rejects_invented_quote_and_state_as_message() -> None:
    gherkin = """
Scenario: Ingresar PIN
  When el usuario ingresa el PIN
  Then el PIN fue ingresado correctamente
"""
    invented = GeneratedCaseCandidate(
        name="Ingresar PIN",
        description="",
        evidence=gherkin,
        justification="test",
        steps=[
            CandidateStep(
                step_number=1,
                action='Ingresar "Hola Mundo"',
                expected_result='Se muestra el mensaje "PIN fue ingresado correctamente".',
            )
        ],
    )
    reasons = validate_llm_case(invented, gherkin, [], "", gherkin)
    assert any("Hola Mundo" in reason for reason in reasons)
    assert any("estado" in reason or "mensaje" in reason for reason in reasons)
    proper = GeneratedCaseCandidate(
        name="Pago mediante Apple Pay",
        description="",
        evidence=gherkin,
        justification="test",
        steps=[CandidateStep(step_number=1, action="Seleccionar Apple Pay", expected_result="Se muestra la pantalla de pago.")],
    )
    assert not any("separador" in reason for reason in validate_llm_case(proper, gherkin, [], "", gherkin))
    glued = GeneratedCaseCandidate(
        name="No mostrar el panel si el evento pertenece al mism El usuario está autentificado",
        description="",
        evidence=gherkin,
        justification="test",
        steps=[CandidateStep(step_number=1, action="Seleccionar el evento", expected_result="No se muestra el panel.")],
    )
    assert any("separador" in reason for reason in validate_llm_case(glued, gherkin, [], "", gherkin))


def test_x5_backtick_identifier_moves_whole_to_technical_reference() -> None:
    cases, _stats = _cases(
        """
Feature: Inicio
  Scenario: Carga exitosa del carrusel
    When el usuario abre el inicio
    Then se emite el evento `home.carousel_loaded.v1`
"""
    )
    case = next(row for row in cases if row.steps)
    tech = case.technical_reference or ""
    assert "home.carousel_loaded.v1" in tech
    visible = " ".join(
        [case.name or "", case.precondition or ""]
        + [f"{step.action} {step.expected_result}" for step in case.steps]
    )
    assert "home.carousel_loaded.v1" not in visible
    assert ". ." not in visible
    assert "=" not in visible
    assert "initiated" not in visible
    assert "Se muestra el carrusel con sus contenidos" in visible


def test_x6_system_when_is_technical_verification_without_a_case() -> None:
    _cases_out, stats = _cases(
        """
Feature: Registro
  Scenario: Procesar campo
    When el sistema procesa el campo del registro
    Then el servicio deja el valor en un estado interno
"""
    )
    assert not any(row.steps for row in _cases_out)
    assert any(row.get("estado") == "verificación técnica" for row in stats.scenario_ledger)


def test_x7_duplicate_titles_use_a_short_separator_not_a_cut_precondition() -> None:
    stats = GenerationStats()
    cases = candidates_from_jira_artifacts(
        _artifacts(
            [
                ("EPC-1", "ST-1", "Feature reproductor en vivo", """
Scenario: Ver detalle
  When el usuario selecciona el contenido
  Then se muestra el detalle
"""),
                ("EPC-1", "ST-2", "Feature guía de canales", """
Scenario: Ver detalle
  Given el usuario está autentificado en la plataforma
  When el usuario selecciona el contenido
  Then se muestra el detalle
"""),
            ]
        ),
        "rn.pdf",
        [],
        lambda *_a: None,
        stats=stats,
    )
    names = [row.name for row in cases if row.steps]
    assert len(names) >= 2
    assert all(" — " in name for name in names)
    assert all("autentific" not in name.lower() for name in names)
    assert all("mism" not in name.lower() for name in names)
    for name in names:
        context = name.split(" — ", 1)[1]
        assert len(context.split()) <= 6


def test_x8_navigation_given_becomes_the_first_step() -> None:
    cases, _stats = _cases(
        """
Feature: Inicio
  Background:
    Given el usuario abre la pantalla de inicio
  Scenario: Ver el detalle
    When el usuario selecciona el primer contenido
    Then se muestra el detalle
"""
    )
    case = next(row for row in cases if row.steps)
    assert len(case.steps) >= 2
    first = case.steps[0]
    assert "inicio" in (first.action or "").lower() or "inicio" in (first.expected_result or "").lower()
    assert (first.expected_result or "").strip()
    plain = _cases(
        """
Scenario: Confirmar
  When el usuario selecciona Confirmar
  Then se muestra el comprobante
"""
    )[0]
    alone = next(row for row in plain if row.steps)
    assert len(alone.steps) == 1
