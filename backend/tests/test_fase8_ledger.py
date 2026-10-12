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
