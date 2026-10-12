"""FASE 8: every functional Gherkin scenario gets a ledger row. Synthetic Gherkin only."""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.schemas.case_generation import GenerationStats
from app.services.gherkin_coverage import candidates_from_jira_artifacts, extract_gherkin_blocks

_SCENARIO_SPLIT = re.compile(
    r"^\s*(?:[-*]\s*)?(Scenario Outline|Scenario|Escenario esquemático|Escenario)\s*:?\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _is_functional_story(item: dict) -> bool:
    issuetype = (item.get("issuetype") or "").strip().lower()
    summary = (item.get("summary") or "").strip().lower()
    if re.search(r"\b(bug|tarea|task|ventana|epic|sub-?task)\b", issuetype):
        return False
    if "story" in issuetype:
        return True
    return summary.startswith("feature") or summary.startswith("user story")


def count_functional_gherkin_scenarios(artifacts: list[dict]) -> int:
    """Independent of the A–G classifier. One row per Scenario/Outline of a functional story."""
    seen: set[tuple[str, str]] = set()
    for epic in artifacts:
        children = list(epic.get("children") or [])
        stories = [row for row in children if _is_functional_story(row)]
        if not stories and _is_functional_story(epic):
            stories = [epic]
        for story in stories:
            blocks = extract_gherkin_blocks(
                story.get("description") or "",
                story.get("acceptance_criteria") or "",
            )
            for block in blocks:
                title = re.sub(r"\s*\([^)]*\)\s*$", "", (block.get("title") or "")).strip()
                key = (str(story.get("key") or ""), re.sub(r"\s+", " ", title.lower()))
                if not title or key in seen:
                    continue
                seen.add(key)
    return len(seen)


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
        {"key": epic, "issuetype": "Technical Epic", "children": children}
        for epic, children in by_epic.items()
    ]


def test_81_every_scenario_has_ledger_row_never_excluded() -> None:
    description = """
Feature: Pago
  Scenario: Completar pago
    When el usuario selecciona Confirmar
    Then se muestra el comprobante
  Scenario: Se envía un evento de checkout
    When el usuario selecciona Confirmar
    Then se envía un evento al servicio de métricas
  Scenario: Flag interno
    When el backend marca el flag
    Then el servicio queda en estado interno
"""
    stats = GenerationStats()
    artifacts = _artifacts(("EPC-1", "ST-1", "Feature pago", description))
    candidates_from_jira_artifacts(artifacts, "rn.pdf", [], lambda *_a: None, stats=stats)
    expected = count_functional_gherkin_scenarios(artifacts)
    ledger = [row for row in stats.scenario_ledger if row.get("scenario")]
    assert len(ledger) == expected
    assert expected >= 3
    assert not any(row.get("estado") == "excluido" for row in ledger)
    assert {row.get("estado") for row in ledger} <= {
        "caso ejecutable",
        "verificación técnica",
        "na_ambiente",
        "pendiente de revisión QC",
    }


def test_81_fixture_ledger_matches_gherkin_count() -> None:
    root = Path(__file__).resolve().parents[1]
    for name in ("dev_epcs_jira.json", "dev2_rn_ios_jira.json"):
        path = root / "tests" / "fixtures" / name
        if not path.exists():
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))["issues"]["nodes"]
        epics = [item for item in raw if item["fields"]["issuetype"]["name"] == "Technical Epic"]
        artifacts = []
        for epic in epics:
            from app.services import jira_generation as jg

            payload = jg._issue_payload(epic)
            kids = sorted(
                (jg._issue_payload(child) for child in raw if (child["fields"].get("parent") or {}).get("key") == epic["key"]),
                key=lambda item: item["key"],
            )
            payload.update(children=kids)
            artifacts.append(payload)
        stats = GenerationStats()
        candidates_from_jira_artifacts(artifacts, "rn.pdf", [], lambda *_a: None, stats=stats)
        expected = count_functional_gherkin_scenarios(artifacts)
        ledger = stats.scenario_ledger
        assert len(ledger) == expected, f"{name}: ledger={len(ledger)} gherkin={expected}"
        assert not any(row.get("estado") == "excluido" for row in ledger)


def test_83_technical_then_with_user_when_is_regression() -> None:
    description = """
Feature: Checkout
  Scenario: Registrar métrica al confirmar
    Given el usuario está en el resumen
    When el usuario selecciona Confirmar
    Then se envía un evento de checkout
    And se muestra el comprobante
"""
    stats = GenerationStats()
    cases = candidates_from_jira_artifacts(
        _artifacts(("EPC-1", "ST-1", "Feature checkout", description)),
        "rn.pdf",
        [],
        lambda *_a: None,
        stats=stats,
    )
    case = next(row for row in cases if row.steps)
    assert any("confirmar" in (step.action or "").lower() for step in case.steps)
    blob = " ".join(step.expected_result or "" for step in case.steps).lower()
    assert "comprobante" in blob or "checkout" in blob
    assert case.technical_reference
    assert "verificación técnica" in (case.technical_reference or "").lower()


def test_84_variant_table_on_examples() -> None:
    description = """
Scenario Outline: Elegir plan
  Given el usuario está en el catálogo
  When el usuario selecciona "<plan>"
  Then se muestra el contenido
  Examples:
    | plan |
    | A    |
    | B    |
"""
    cases = candidates_from_jira_artifacts(
        _artifacts(("EPC-1", "ST-1", "Feature catálogo", description)),
        "rn.pdf",
        [],
        lambda *_a: None,
    )
    assert cases
    table = cases[0].variant_table or ""
    assert "Condición" in table
    assert "A" in table or "plan" in (cases[0].test_data or "").lower()


def test_f2_validator_requires_ui_literals_not_endpoints() -> None:
    from app.schemas.case_generation import CandidateStep, GeneratedCaseCandidate
    from app.services.scenario_llm import required_ui_literals, validate_llm_case

    gherkin = """
Scenario: Guardar ficha
  When el usuario selecciona "Guardar"
  Then se muestra "Ficha guardada"
  And el servicio responde en "/catalog/v1/cards"
  And se envía el flag "saveCard =true"
"""
    literals = required_ui_literals(gherkin)
    assert "Guardar" in literals
    assert "Ficha guardada" in literals
    assert not any("/catalog" in item for item in literals)
    assert not any("=" in item for item in literals)
    tech_gherkin = gherkin + '\n  And el servicio responde "200"\n  And el header "Authorization" es válido\n'
    tech_lits = required_ui_literals(tech_gherkin)
    assert "200" not in tech_lits
    assert "Authorization" not in tech_lits

    valid = GeneratedCaseCandidate(
        name="Guardar ficha",
        description="",
        evidence=gherkin,
        justification="test",
        steps=[
            CandidateStep(
                step_number=1,
                action='Seleccionar "Guardar"',
                expected_result='Se muestra "Ficha guardada".',
            )
        ],
    )
    assert validate_llm_case(valid, gherkin, []) == []

    missing = GeneratedCaseCandidate(
        name="Guardar ficha",
        description="",
        evidence=gherkin,
        justification="test",
        steps=[
            CandidateStep(
                step_number=1,
                action="Seleccionar confirmar",
                expected_result="Se muestra el comprobante.",
            )
        ],
    )
    reasons = validate_llm_case(missing, gherkin, [])
    assert any("Guardar" in reason or "Ficha guardada" in reason for reason in reasons)

    with_api = GeneratedCaseCandidate(
        name="Guardar ficha",
        description="",
        evidence=gherkin,
        justification="test",
        steps=[
            CandidateStep(
                step_number=1,
                action='Seleccionar "Guardar"',
                expected_result='Se muestra "Ficha guardada" y POST "/catalog/v1/cards".',
            )
        ],
    )
    assert any("endpoint" in reason for reason in validate_llm_case(with_api, gherkin, []))


def test_f1_pending_and_tech_with_user_when_are_llm_eligible() -> None:
    from app.services.gherkin_coverage import build_coverage_inventory
    from app.services.scenario_llm import _llm_eligible

    pending = """
Scenario: Flag interno
  When el backend marca el flag
  Then el servicio queda en estado interno
"""
    tech_user = """
Scenario: Registrar métrica al confirmar
  When el usuario selecciona Confirmar
  Then se envía un evento de checkout
"""
    stats = GenerationStats()
    units = build_coverage_inventory(
        _artifacts(
            ("EPC-1", "ST-1", "Feature pago", pending),
            ("EPC-1", "ST-2", "Feature checkout", tech_user),
        ),
        "rn.pdf",
        stats=stats,
    )
    gherkin_units = [unit for unit in units if (unit.source_origin or "gherkin") == "gherkin"]
    assert gherkin_units
    assert any(_llm_eligible(unit) for unit in gherkin_units)
    pending_units = [
        unit for unit in gherkin_units if any(str(rule).startswith("pendiente-qc") for rule in (unit.applied_rules or []))
    ]
    assert pending_units
    assert all(_llm_eligible(unit) for unit in pending_units)
