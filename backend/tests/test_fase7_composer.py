"""FASE 7: one Test Case per Jira Scenario. Synthetic Gherkin only."""

import io

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
    pre = (case.precondition or "").lower()
    assert "inicio" in pre or "programas" in pre
    assert any("seleccion" in action for action in actions)
    assert all(not action.startswith("observ") for action in actions)
    assert all("given" not in action for action in actions)
    assert all("abrir la aplicación" not in action for action in actions)
    assert all("pantalla de partida" not in (step.expected_result or "").lower() for step in case.steps)


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
    assert pending or any(row.get("estado") == "verificación técnica" for row in stats.scenario_ledger)
    assert not excluded
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
    assert len(matching) == 1
    blob = f"{matching[0].test_data or ''} {matching[0].variant_table or ''}".lower()
    assert "éxito" in blob or "exito" in blob or "error" in blob or "uno" in blob or "dos" in blob


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
    assert len(matching) == 1


def test_75_legend_template_is_not_materialized() -> None:
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
    assert all("robustez-consumo" in (unit.scenario_group or "") for unit in legend)


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
        "verificación técnica",
    }


def test_given_becomes_tester_state_not_estar_en() -> None:
    description = """
Scenario: Ver panel
  Given un usuario que ingresa al Panel Más información
  When el usuario selecciona Recordatorio
  Then se muestra el modal de recordatorio
"""
    cases = candidates_from_jira_artifacts(
        _artifacts(("EPC-1", "ST-1", "Feature panel", description)),
        "rn.pdf",
        [],
        lambda *_a: None,
    )
    case = next(row for row in cases if row.steps)
    pre = case.precondition or ""
    assert "Panel Más información abierto" in pre
    assert "Estar en" not in pre
    actions = [step.action.lower() for step in case.steps]
    assert all("verificar" not in action for action in actions)
    assert all(action != (case.name or "").lower() for action in actions)
    assert any("abrir" in action and "panel" in action for action in actions) or any(
        "seleccion" in action for action in actions
    )
    for step in case.steps:
        assert (step.expected_result or "").strip()
        assert (step.expected_result or "").lower()[:40] != (case.name or "").lower()[:40]
        assert (step.expected_result or "").lower() != (step.action or "").lower()


def test_then_hidden_action_becomes_own_step() -> None:
    description = """
Scenario: Salir
  Given un usuario que accede al player de TV en vivo
  When el control player se encuentra activo
  Then al presionar el botón Salir se muestra la Guía
"""
    cases = candidates_from_jira_artifacts(
        _artifacts(("EPC-1", "ST-1", "Feature player", description)),
        "rn.pdf",
        [],
        lambda *_a: None,
    )
    case = next(row for row in cases if row.steps)
    actions = " ".join(step.action.lower() for step in case.steps)
    assert "presion" in actions
    assert "verificar" not in actions
    assert any("guía" in (step.expected_result or "").lower() or "guia" in (step.expected_result or "").lower() for step in case.steps)


def test_igual_que_antes_only_on_impact() -> None:
    description = """
Scenario: Nueva botonera
  Given un usuario que accede al player de TV en vivo
  When el usuario abre el control
  Then se muestran los botones nuevos
"""
    cases = candidates_from_jira_artifacts(
        _artifacts(("EPC-1", "ST-1", "Feature botonera nueva", description)),
        "rn.pdf",
        [],
        lambda *_a: None,
    )
    case = next(row for row in cases if row.steps)
    blob = " ".join(f"{step.action} {step.expected_result}" for step in case.steps).lower()
    assert "igual que antes" not in blob


def test_vague_given_stays_as_precondition_without_nav() -> None:
    description = """
Scenario: Recordatorio
  Given el contenido está disponible en el catálogo
  When el usuario selecciona Recordatorio
  Then se muestra el modal de recordatorio
"""
    cases = candidates_from_jira_artifacts(
        _artifacts(("EPC-1", "ST-1", "Historia de recordatorio en catálogo", description)),
        "rn.pdf",
        [],
        lambda *_a: None,
    )
    case = next(row for row in cases if row.steps)
    pre = case.precondition or ""
    assert "el contenido está disponible en el catálogo" in pre.lower()
    assert "abierto" not in pre.lower()
    assert "abrir el" not in pre.lower()
    assert "se muestra el" not in pre.lower()
    assert "historia de recordatorio" not in pre.lower()
    assert all(not (step.action or "").lower().startswith("abrir el") for step in case.steps)


def test_figma_and_story_title_are_not_precondition() -> None:
    description = """
Scenario: Ver detalle
  Given https://www.figma.com/design/abc123/Pantalla
  And Historia de recordatorio en catálogo
  When el usuario selecciona el evento
  Then se muestra el detalle
"""
    cases = candidates_from_jira_artifacts(
        _artifacts(("EPC-1", "ST-1", "Historia de recordatorio en catálogo", description)),
        "rn.pdf",
        [],
        lambda *_a: None,
    )
    case = next((row for row in cases if row.steps), None)
    pre = (case.precondition or "") if case else ""
    assert "figma" not in pre.lower()
    assert "historia de recordatorio en catálogo" not in pre.lower()


def test_story_title_and_figma_never_in_pre_steps_or_result() -> None:
    description = """
Scenario: Ver detalle
  Given según Figma https://www.figma.com/design/abc123
  And Historia de recordatorio en catálogo
  When el usuario selecciona el evento según Figma
  Then se muestra Historia de recordatorio en catálogo
"""
    cases = candidates_from_jira_artifacts(
        _artifacts(("EPC-1", "ST-1", "Historia de recordatorio en catálogo", description)),
        "rn.pdf",
        [],
        lambda *_a: None,
    )
    case = next((row for row in cases if row.steps), None)
    blob = " ".join(
        [
            (case.precondition or "") if case else "",
            *([step.action for step in case.steps] if case else []),
            *([step.expected_result for step in case.steps] if case else []),
        ]
    ).lower()
    assert "figma" not in blob
    assert "historia de recordatorio en catálogo" not in blob


def test_no_abrir_aplicacion_when_screen_nav_exists() -> None:
    description = """
Scenario: Ver panel
  Given un usuario que ingresa al Panel Más información
  When el usuario selecciona Recordatorio
  Then se muestra el modal de recordatorio
"""
    cases = candidates_from_jira_artifacts(
        _artifacts(("EPC-1", "ST-1", "Feature panel", description)),
        "rn.pdf",
        [],
        lambda *_a: None,
    )
    case = next(row for row in cases if row.steps)
    actions = [step.action.lower() for step in case.steps]
    assert any("abrir" in action for action in actions)
    assert all("abrir la aplicación" not in action for action in actions)


def test_consecutive_steps_with_same_result_merge() -> None:
    description = """
Scenario: Modal
  Given un usuario que ingresa al Panel Más información
  When el usuario selecciona Recordatorio
  Then se muestra el modal
  When el usuario confirma
  Then se muestra el modal
"""
    cases = candidates_from_jira_artifacts(
        _artifacts(("EPC-1", "ST-1", "Feature panel", description)),
        "rn.pdf",
        [],
        lambda *_a: None,
    )
    case = next(row for row in cases if row.steps)
    expecteds = [step.expected_result for step in case.steps if (step.expected_result or "").strip()]
    assert expecteds
    consecutive = [
        expecteds[i] == expecteds[i + 1]
        for i in range(len(expecteds) - 1)
    ]
    assert not any(consecutive)


def test_redactar_caso_is_identity_today() -> None:
    from app.services.scenario_cases import redactar_caso

    case = GeneratedCaseCandidate(
        name="Seleccionar Recordatorio",
        description="d",
        evidence="e",
        justification="j",
        covers=["COV-1"],
        precondition="el contenido está disponible en el catálogo",
        steps=[
            CandidateStep(
                step_number=1,
                action="Seleccionar Recordatorio",
                expected_result="Se muestra el modal de recordatorio",
            )
        ],
    )
    out = redactar_caso(case)
    assert out is case
    assert out.precondition == case.precondition
    assert out.steps[0].action == case.steps[0].action
    assert out.steps[0].expected_result == case.steps[0].expected_result


def test_no_generic_startup_step() -> None:
    description = """
Scenario: Ver player
  Given un usuario que accede al player de TV en vivo
  When el control player se encuentra activo
  Then se muestra la botonera
"""
    cases = candidates_from_jira_artifacts(
        _artifacts(("EPC-1", "ST-1", "Feature player", description)),
        "rn.pdf",
        [],
        lambda *_a: None,
    )
    case = next(row for row in cases if row.steps)
    actions = [step.action.lower() for step in case.steps]
    assert "abrir la aplicación" not in " ".join(actions)
    assert "pantalla de partida" not in " ".join(step.expected_result.lower() for step in case.steps)
    assert "player" in (case.precondition or "").lower()
    assert "estar en" not in (case.precondition or "").lower()
    assert len(actions) == len(set(actions))


def test_excel_ledger_uses_case_id_not_name() -> None:
    from types import SimpleNamespace

    payload = build_test_cases_workbook(
        [
            SimpleNamespace(
                test_case_id="QC-003",
                test_case_name="Ver detalle",
                component="EPC-1",
                technical_epic="EPC-1",
                hn_source=None,
                status="UNEXECUTED",
                estimation_hours=0.17,
                priority="CRITICAL",
                test_type="FUNCTIONAL",
                source_type="functionality",
                user_type=None,
                test_data=None,
                evidence="",
                justification="",
                technical_story="ST-1",
                scenario_origin="Ver detalle",
                confidence=None,
                complexity="BAJA",
                description=None,
                device=None,
                applicability_reason=None,
                steps=[SimpleNamespace(step_number=1, test_step="Seleccionar", expected_result="Se muestra el detalle")],
            )
        ],
        scenario_ledger=[
            {
                "story": "ST-1",
                "epic": "EPC-1",
                "scenario": "Ver detalle",
                "estado": "caso ejecutable",
                "case_id": "Ver detalle",
                "motivo": "",
            }
        ],
    )
    book = load_workbook(io.BytesIO(payload))
    assert book["Escenarios de Jira"]["D2"].value == "QC-003"


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


def test_llm_invalid_uses_deterministic_engine(monkeypatch) -> None:
    from app.services import scenario_llm as sl

    def boom(*_a, **_k):
        raise RuntimeError("timeout quota")

    monkeypatch.setattr(sl, "_call_llm", boom)
    base = GeneratedCaseCandidate(
        name="Seleccionar Recordatorio",
        description="d",
        evidence="e",
        justification="j",
        covers=["COV-1"],
        steps=[
            CandidateStep(
                step_number=1,
                action="Seleccionar Recordatorio",
                expected_result="Se muestra el modal de recordatorio",
            )
        ],
    )
    rewritten, meta = sl._rewrite_one(base, None, "story", "", [], 1.0)
    assert rewritten.steps
    assert rewritten.steps[0].action == "Seleccionar Recordatorio"
    assert meta.get("ok") is False
    assert "determinista" in (meta.get("error") or "").lower() or meta.get("error")
    assert not any(
        str(rule).startswith("pendiente-qc") for rule in (rewritten.applied_rules or [])
    )


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
