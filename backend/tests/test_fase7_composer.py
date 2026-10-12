"""FASE 7: one Test Case per Jira Scenario. Synthetic Gherkin only."""

import io
import re

from openpyxl import load_workbook

from app.schemas.case_generation import CandidateStep, GeneratedCaseCandidate, GenerationStats
from app.services.gherkin_coverage import build_coverage_inventory, candidates_from_jira_artifacts
from app.services.scenario_cases import align_llm_to_deterministic, llm_rewrite_is_safe
from app.services.test_case_export import build_test_cases_workbook


def _artifacts(*stories: tuple[str, str, str, str]) -> list[dict]:
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
        {
            "key": epic,
            "issuetype": "Technical Epic",
            "children": children,
        }
        for epic, children in by_epic.items()
    ]


def test_71_atomized_thens_reunite_into_one_scenario_case() -> None:
    description = """
Scenario: Confirmar compra
  Given el usuario está en el resumen
  When el usuario selecciona Confirmar
  Then se muestra el comprobante
  And se muestra el botón "Descargar"
"""
    stats = GenerationStats()
    cases = candidates_from_jira_artifacts(
        _artifacts(("EPC-1", "ST-1", "Feature compra", description)),
        "rn.pdf",
        [],
        lambda *_a: None,
        stats=stats,
    )
    exe = [row for row in cases if row.applicability != "na_ambiente"]
    matching = [row for row in exe if "confirmar compra" in (row.name or "").lower()]
    assert len(matching) == 1
    blob = " ".join(step.expected_result for step in matching[0].steps).lower()
    assert "comprobante" in blob
    assert "descargar" in blob


def test_72_background_nav_becomes_first_infinitive_steps() -> None:
    description = """
Feature: Evento futuro
  Background:
    Given el usuario visualiza la pantalla de inicio
    And el usuario da clic en el botón "Programas"
  Scenario: Ver detalle
    When el usuario selecciona el evento
    Then se muestra el detalle del evento
"""
    cases = candidates_from_jira_artifacts(
        _artifacts(("EPC-1", "ST-1", "Feature: Evento futuro", description)),
        "rn.pdf",
        [],
        lambda *_a: None,
    )
    case = next(row for row in cases if "detalle" in (row.name or "").lower())
    actions = [step.action.lower() for step in case.steps]
    assert any(action.startswith("abrir") for action in actions)
    assert any("programas" in action for action in actions)
    assert any("seleccion" in action for action in actions)
    assert all(not action.startswith("observ") for action in actions)


def test_72_no_user_action_is_pending_qc() -> None:
    description = """
Scenario: Estado interno
  Given el token de sesión expiró
  When el backend marca el flag
  Then el servicio queda en estado interno
"""
    stats = GenerationStats()
    cases = candidates_from_jira_artifacts(
        _artifacts(("EPC-1", "ST-1", "Feature interna", description)),
        "rn.pdf",
        [],
        lambda *_a: None,
        stats=stats,
    )
    pending = [
        row
        for row in stats.scenario_ledger
        if row.get("estado") == "pendiente de revisión QC"
    ]
    excluded = [row for row in stats.scenario_ledger if row.get("estado") == "excluido"]
    assert pending or excluded
    assert all(row.get("estado") for row in stats.scenario_ledger)


def test_73_outline_same_then_folds_examples_into_test_data() -> None:
    description = """
Scenario Outline: Elegir opción
  Given el usuario está en el catálogo
  When el usuario selecciona "<opcion>"
  Then se muestra el contenido elegido
  Examples:
    | opcion |
    | A      |
    | B      |
"""
    cases = candidates_from_jira_artifacts(
        _artifacts(("EPC-1", "ST-1", "Feature catálogo", description)),
        "rn.pdf",
        [],
        lambda *_a: None,
    )
    matching = [row for row in cases if "elegir opción" in (row.name or "").lower()]
    assert len(matching) == 1
    data = (matching[0].test_data or "").lower()
    assert "a" in data and "b" in data


def test_73_outline_different_then_splits_and_puts_value_in_title() -> None:
    description = """
Scenario Outline: Resultado según tipo
  Given el usuario está en el formulario
  When el usuario selecciona Continuar
  Then se muestra "<resultado>"
  Examples:
    | tipo | resultado |
    | uno  | éxito     |
    | dos  | error     |
"""
    cases = candidates_from_jira_artifacts(
        _artifacts(("EPC-1", "ST-1", "Feature formulario", description)),
        "rn.pdf",
        [],
        lambda *_a: None,
    )
    matching = [row for row in cases if "resultado según tipo" in (row.name or "").lower()]
    assert len(matching) >= 2
    names = " ".join(row.name.lower() for row in matching)
    assert "éxito" in names or "exito" in names or "error" in names or "uno" in names or "dos" in names


def test_74_repeated_scenario_keeps_story_context_in_title() -> None:
    shared = """
Scenario: Ver detalle
  Given el usuario está en el listado
  When el usuario selecciona el evento
  Then se muestra el detalle
"""
    cases = candidates_from_jira_artifacts(
        _artifacts(
            ("EPC-1", "ST-FUT", "Feature: evento futuro", shared),
            ("EPC-1", "ST-PRES", "Feature: evento presente", shared),
        ),
        "rn.pdf",
        [],
        lambda *_a: None,
    )
    matching = [row for row in cases if "ver detalle" in (row.name or "").lower()]
    assert len(matching) == 2
    names = {row.name for row in matching}
    assert len(names) == 2
    joined = " ".join(names).lower()
    assert "futuro" in joined
    assert "presente" in joined
    assert not any("(" in name and name.rstrip()[-2].isdigit() for name in names)


def test_75_legend_template_is_na_ambiente_not_silent_drop() -> None:
    description = """
Feature: Implementar banner con políticas de cookies
  Scenario: Mostrar banner
    When el usuario abre la landing
    Then se muestra el banner
  Scenario: No se logra obtener una llave
    Given una llave no se encuentra en apa/metadata
    When la aplicación intenta construir la leyenda
    Then el espacio donde debería mostrarse la leyenda debe mostrar la llave
"""
    stats = GenerationStats()
    units = build_coverage_inventory(
        _artifacts(("EPC-B", "ST-B", "Feature: Implementar banner con políticas de cookies", description)),
        "rn.pdf",
        stats=stats,
    )
    legend = [unit for unit in units if "no se logra obtener una llave" in (unit.scenario or "").lower()]
    assert legend
    assert all(unit.applicability == "na_ambiente" for unit in legend)


def test_76_every_functional_scenario_has_ledger_state() -> None:
    description = """
Scenario: Acción visible
  Given el usuario está en el flujo
  When el usuario selecciona Continuar
  Then se muestra el resultado
Scenario: Configuración remota vacía
  Given la configuración remota no se logra obtener
  When el usuario abre el flujo
  Then se muestra el estado vacío en pantalla
"""
    stats = GenerationStats()
    candidates_from_jira_artifacts(
        _artifacts(("EPC-1", "ST-1", "Feature visible", description)),
        "rn.pdf",
        [],
        lambda *_a: None,
        stats=stats,
    )
    assert stats.scenario_ledger
    assert all(row.get("estado") for row in stats.scenario_ledger)
    assert {row.get("estado") for row in stats.scenario_ledger} <= {
        "caso ejecutable",
        "na_ambiente",
        "pendiente de revisión QC",
        "excluido",
    }


def test_76_excel_has_escenarios_de_jira_sheet() -> None:
    payload = build_test_cases_workbook(
        [],
        scenario_ledger=[
            {
                "story": "ST-1",
                "scenario": "Ver detalle",
                "estado": "caso ejecutable",
                "case_id": "QC-001",
                "motivo": "",
            }
        ],
    )
    book = load_workbook(io.BytesIO(payload))
    assert "Escenarios de Jira" in book.sheetnames
    sheet = book["Escenarios de Jira"]
    assert sheet["A2"].value == "ST-1"
    assert sheet["C2"].value == "caso ejecutable"


def test_77_unsafe_llm_rewrite_falls_back_to_deterministic() -> None:
    base = GeneratedCaseCandidate(
        name='Seleccionar "Confirmar"',
        description="d",
        evidence="e",
        justification="j",
        covers=["COV-1"],
        steps=[
            CandidateStep(step_number=1, action='Seleccionar "Confirmar"', expected_result='Se muestra "OK"'),
            CandidateStep(step_number=2, action="Abrir el detalle", expected_result="Se muestra el detalle"),
        ],
    )
    llm = base.model_copy(
        update={
            "steps": [CandidateStep(step_number=1, action="Observar el resultado", expected_result="ok")],
            "covers": ["COV-1"],
        }
    )
    assert llm_rewrite_is_safe(base, llm) is False
    aligned = align_llm_to_deterministic([base], [llm])
    assert aligned[0] is base


def test_711_nav_without_generic_result_is_compacted() -> None:
    description = """
Feature: Evento
  Background:
    Given el usuario ingresa a la pantalla A
    And el usuario abre el panel B
    And el usuario selecciona C
  Scenario: Ver comprobante
    Given el usuario está en C
    When el usuario selecciona Confirmar
    Then se muestra el comprobante
"""
    cases = candidates_from_jira_artifacts(
        _artifacts(("EPC-1", "ST-1", "Feature evento", description)),
        "rn.pdf",
        [],
        lambda *_a: None,
    )
    case = next(row for row in cases if "comprobante" in (row.name or "").lower())
    assert all("se observa el comportamiento" not in (step.expected_result or "").lower() for step in case.steps)
    assert all((step.expected_result or "").strip() for step in case.steps)
    compacted = any(">" in (step.action or "") or (step.action or "").lower().startswith("navegar") for step in case.steps)
    named = all(
        re.search(r"se muestra", step.expected_result or "", re.I) for step in case.steps[:-1] or case.steps
    )
    assert compacted or named or len(case.steps) <= 3


def test_712_system_when_uses_background_nav() -> None:
    description = """
Feature: Pago
  Background:
    Given el usuario ingresa a la pantalla de pago
  Scenario: Procesar información
    When la información es procesada
    Then se muestra el comprobante
"""
    cases = candidates_from_jira_artifacts(
        _artifacts(("EPC-1", "ST-1", "Feature pago", description)),
        "rn.pdf",
        [],
        lambda *_a: None,
    )
    exe = [row for row in cases if row.steps]
    assert exe
    assert any("comprobante" in (step.expected_result or "").lower() for step in exe[0].steps)
    assert all(row.steps for row in exe)


def test_713_precondition_has_no_feature_or_api() -> None:
    description = """
Feature: Flujo
  Background:
    Given el usuario está autenticado
  Scenario: Abrir detalle
    Given se muestra el listado
    When el usuario selecciona el evento
    Then se muestra el detalle
"""
    cases = candidates_from_jira_artifacts(
        _artifacts(("EPC-1", "ST-1", "Feature 01: Validar PIN", description)),
        "rn.pdf",
        [],
        lambda *_a: None,
    )
    for case in cases:
        assert not re.search(r"Feature\b|API|servicio \"|response\.", case.precondition or "")


def test_714_outline_uses_example_value_not_column_name() -> None:
    description = """
Scenario Outline: Elegir guía
  Given el usuario está en vivo
  When el usuario abre la guía <Guía>
  Then se muestra la guía
  Examples:
    | Guía     |
    | mini epg |
    | full epg |
"""
    cases = candidates_from_jira_artifacts(
        _artifacts(("EPC-1", "ST-1", "Feature guía", description)),
        "rn.pdf",
        [],
        lambda *_a: None,
    )
    blob = " ".join(
        " ".join(
            [row.name or "", row.test_data or ""]
            + [f"{step.action} {step.expected_result or ''}" for step in row.steps]
        )
        for row in cases
    ).lower()
    assert "<guía>" not in blob and "<guia>" not in blob
    assert "mini epg" in blob or "full epg" in blob


def test_714b_user_when_always_becomes_a_step() -> None:
    description = """
Scenario: Digitar PIN
  Given se muestra la pantalla de PIN
  When el usuario digita un número 4
  Then se muestra el dígito
"""
    cases = candidates_from_jira_artifacts(
        _artifacts(("EPC-1", "ST-1", "Feature pin", description)),
        "rn.pdf",
        [],
        lambda *_a: None,
    )
    case = next(row for row in cases if "digitar" in (row.name or "").lower() or "pin" in (row.name or "").lower())
    assert case.steps
    assert any("digit" in (step.action or "").lower() or "ingres" in (step.action or "").lower() for step in case.steps)


def test_714c_sibling_scenarios_keep_their_own_test_data() -> None:
    description = """
Scenario: Límite corto
  Given el valor = 120
  When el usuario selecciona Guardar
  Then se muestra el límite corto
Scenario: Límite largo
  Given el valor = 1350
  When el usuario selecciona Guardar
  Then se muestra el límite largo
"""
    cases = candidates_from_jira_artifacts(
        _artifacts(("EPC-1", "ST-1", "Feature límites", description)),
        "rn.pdf",
        [],
        lambda *_a: None,
    )
    corto = next(row for row in cases if "corto" in (row.name or "").lower())
    largo = next(row for row in cases if "largo" in (row.name or "").lower())
    corto_blob = " ".join([corto.test_data or "", corto.precondition or ""] + [s.action for s in corto.steps])
    largo_blob = " ".join([largo.test_data or "", largo.precondition or ""] + [s.action for s in largo.steps])
    assert "120" in corto_blob
    assert "1350" in largo_blob
    assert "1350" not in corto_blob
    assert "120" not in largo_blob


def test_714_table_rows_are_not_steps() -> None:
    description = """
Scenario: Panel de opciones
  Given el usuario está en el flujo
  When el usuario abre el panel
  Then se muestra el panel de opciones
    | elemento | valor |
    | título | OPCIONES |
    | botón | Cancelar grabación |
"""
    cases = candidates_from_jira_artifacts(
        _artifacts(("EPC-1", "ST-1", "Feature panel", description)),
        "rn.pdf",
        [],
        lambda *_a: None,
    )
    assert cases, "expected at least one scenario case"
    case = next((row for row in cases if row.steps), cases[0])
    assert all(not re.search(r"\d+\s*x\s*\d+\s*px|:.*:.*:", step.action or "") for step in case.steps)
    expected = " ".join(step.expected_result for step in case.steps).lower()
    assert "opciones" in expected or "cancelar" in expected
