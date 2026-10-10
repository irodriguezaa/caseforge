"""FASE 6A: generic invariants and synthetic Gherkin for R1–R7."""

from app.schemas.case_generation import CandidateStep, GeneratedCaseCandidate, GenerationStats
from app.services.coverage_quality import given_requires_remote_setup, quality_gate
from app.services.executability import parse_scenario_clauses
from app.services.gherkin_coverage import (
    build_coverage_inventory,
    parse_gherkin_blocks,
    sanitize_user_text,
)
from app.services.test_case_export import _skip_zephyr


def _story(key: str, summary: str, description: str, issuetype: str = "Technical Story") -> dict:
    return {
        "key": key,
        "summary": summary,
        "issuetype": issuetype,
        "description": description,
        "acceptance_criteria": "",
    }


def _epic(children: list[dict]) -> dict:
    return {
        "key": "EPC-1",
        "summary": "Feature parent",
        "issuetype": "Technical Epic",
        "description": "",
        "acceptance_criteria": "",
        "children": children,
    }


def test_r1_only_functional_stories_are_inventory_sources() -> None:
    gherkin = """
Scenario: El resultado se muestra en pantalla
  Given el usuario está en el flujo
  When el usuario selecciona Continuar
  Then se muestra el resultado en pantalla
"""
    stats = GenerationStats()
    units = build_coverage_inventory(
        [
            _epic(
                [
                    _story("BUG-1", "falla", "se muestra la confirmación sin solicitar dato", "QA Bug"),
                    _story("ST-1", "Feature visible", gherkin, "Technical Story"),
                    _story("TASK-1", "hacer deploy", "Given nada", "Tarea"),
                ]
            )
        ],
        "rn.pdf",
        stats=stats,
    )
    keys = {unit.story_key for unit in units}
    assert "ST-1" in keys
    assert "BUG-1" not in keys
    assert "TASK-1" not in keys
    assert any("QA Bug" in row for row in stats.inventory_exclusions)


def test_r3_headless_gwt_is_a_scenario() -> None:
    blocks = parse_gherkin_blocks(
        """
Given el usuario está autenticado
When el usuario selecciona Guardar
Then se muestra el comprobante
"""
    )
    assert len(blocks) == 1
    assert "comprobante" in blocks[0]["title"].lower()


def test_r3_headings_and_table_rows_are_not_units() -> None:
    stats = GenerationStats()
    units = build_coverage_inventory(
        [
            _epic(
                [
                    _story(
                        "ST-2",
                        "Feature lista",
                        """
## Alcance técnico
- servicio A
| fps | cpu |
| 30 | 10% |
Criterios de compilación y cobertura unitaria al 80%.
""",
                    )
                ]
            )
        ],
        "rn.pdf",
        stats=stats,
    )
    titles = " ".join(unit.scenario for unit in units)
    assert "fps" not in titles.lower()
    assert "cobertura unitaria" not in titles.lower()


def test_r4_technical_then_is_translated_from_same_story() -> None:
    stats = GenerationStats()
    units = build_coverage_inventory(
        [
            _epic(
                [
                    _story(
                        "ST-3",
                        "Feature datos",
                        """
Scenario: Presenta la información
  Given el usuario está en el detalle
  When el usuario abre el detalle
  Then se muestra la información actualizada en pantalla

Scenario: Refresca el servicio
  Given el usuario está en el detalle
  When el usuario actualiza
  Then se debe realizar una nueva llamada GET /services/item y actualizar la información en el dispositivo
""",
                    )
                ]
            )
        ],
        "rn.pdf",
        stats=stats,
    )
    assert units
    assert any("then-tecnico-traducido" in (unit.applied_rules or []) for unit in units) or any(
        "pantalla" in (unit.observable_then or [""])[0].lower() for unit in units if unit.observable_then
    )


def test_r5_dedupe_is_per_story_not_per_epic() -> None:
    shared = """
Scenario: Acción común
  Given el usuario está en el flujo
  When el usuario selecciona Confirmar
  Then se muestra la confirmación
"""
    stats = GenerationStats()
    units = build_coverage_inventory(
        [
            _epic(
                [
                    _story("ST-A", "Feature uno", shared),
                    _story("ST-B", "Feature dos", shared),
                ]
            )
        ],
        "rn.pdf",
        stats=stats,
    )
    stories = [unit.story_key for unit in units if "confirmación" in (unit.scenario or "").lower() or "confirmacion" in (unit.scenario or "").lower() or "Acción común" in (unit.scenario or "")]
    assert "ST-A" in {unit.story_key for unit in units}
    assert "ST-B" in {unit.story_key for unit in units}


def test_r6_remote_given_is_na_ambiente() -> None:
    assert given_requires_remote_setup(
        "Given la configuración remota está vacía y no se logra obtener el parámetro"
    )
    stats = GenerationStats()
    units = build_coverage_inventory(
        [
            _epic(
                [
                    _story(
                        "ST-4",
                        "Feature config",
                        """
Scenario: Sin configuración remota
  Given la configuración remota no se logra obtener
  When el usuario abre el flujo
  Then se muestra el estado vacío en pantalla
""",
                    )
                ]
            )
        ],
        "rn.pdf",
        stats=stats,
    )
    assert units
    assert any(unit.applicability == "na_ambiente" for unit in units)


def test_r7_given_is_never_expected_and_tables_attach() -> None:
    parsed = parse_scenario_clauses(
        """
Given se muestra la pantalla de inicio
When el usuario ingresa el dato
And GET /services/x status 200
And el usuario selecciona Continuar
Then se permite iniciar la acción
And se listan los valores
| col | valor |
| a | 1 |
"""
    )
    assert "se muestra la pantalla de inicio" in parsed["given"]
    assert "se muestra la pantalla de inicio" not in parsed["expected"]
    assert any("Continuar" in item for item in parsed["actions"])
    assert not any(item.strip().startswith("GET") for item in parsed["actions"])
    assert any("col: a" in item or "a: 1" in item or "col:" in item for item in parsed["expected"])


def test_r7_quoted_ui_text_is_kept() -> None:
    assert "Continuar" in sanitize_user_text('El usuario selecciona "Continuar"')
    assert "foo_bar" not in sanitize_user_text('invoca "foo_bar" en el servicio')


def test_r8_quality_gate_marks_and_skips_zephyr() -> None:
    bad = GeneratedCaseCandidate(
        name="Given que el usuario navega",
        description="x",
        evidence="e",
        justification="j",
        steps=[CandidateStep(step_number=1, action="el usuario ingresa al flujo correspondiente", expected_result="Given que el usuario navega")],
        related_jira="BUG-9",
    )
    gated = quality_gate([bad])[0]
    assert gated.review_required is True
    assert any(rule.startswith("quality-gate:") for rule in gated.applied_rules)
    from types import SimpleNamespace

    persisted = SimpleNamespace(applicability_reason="quality-gate: quality-gate:titulo-gherkin")
    assert _skip_zephyr(persisted) is True
