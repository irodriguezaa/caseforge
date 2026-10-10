"""FASE 6B: flow composition and writing standard. Synthetic Gherkin only."""

from app.schemas.case_generation import CoverageUnit, GenerationStats
from app.services.case_composer import (
    compose_inventory,
    compose_story_units,
    phrases_similar,
    strip_title_prefix,
    to_infinitive,
    validate_composed_candidates,
)
from app.services.gherkin_coverage import build_coverage_inventory


def _unit(**kwargs) -> CoverageUnit:
    data = {
        "coverage_id": "COV-001",
        "role": "G",
        "behavior": "resultado",
        "scenario": "resultado",
        "evidence": "e",
        "body": "",
        "story_key": "ST-1",
        "artifact_key": "EPC-1",
        "applicability": "ejecutable",
    }
    data.update(kwargs)
    return CoverageUnit(**data)


def test_infinitive_and_title_prefix() -> None:
    assert to_infinitive("El usuario selecciona Continuar") == "Seleccionar Continuar"
    assert strip_title_prefix("Validar: se muestra el resultado") == "se muestra el resultado"


def test_chained_given_becomes_steps_of_one_case() -> None:
    artifacts = [
        {
            "key": "EPC-1",
            "issuetype": "Technical Epic",
            "children": [
                {
                    "key": "ST-1",
                    "issuetype": "Technical Story",
                    "summary": "Feature flujo",
                    "description": """
Scenario: Abre el menú
  When el usuario abre el menú de opciones
  Then se muestra el menú de opciones
Scenario: Confirma la acción
  Given se muestra el menú de opciones
  When el usuario selecciona Confirmar
  Then se muestra el comprobante
""",
                    "acceptance_criteria": "",
                }
            ],
        }
    ]
    units = build_coverage_inventory(artifacts, "rn.pdf")
    drafts = compose_story_units([u for u in units if u.story_key == "ST-1"])
    assert drafts
    longest = max(drafts, key=lambda d: len(d.steps))
    assert len(longest.steps) >= 2
    actions = " ".join(step.action for step in longest.steps)
    assert "Abrir" in actions or "abre" in actions.lower()
    assert "Seleccionar" in actions or "Confirmar" in actions
    assert all(step.covered_unit_ids for step in longest.steps)


def test_same_expected_variants_fold() -> None:
    a = _unit(
        coverage_id="COV-001",
        user_action="el usuario selecciona la opción",
        observable_then=["se muestra el mismo resultado"],
        body="When el usuario selecciona la opción\nThen se muestra el mismo resultado",
        extra_test_data="tipo=A",
    )
    b = _unit(
        coverage_id="COV-002",
        user_action="el usuario selecciona la opción",
        observable_then=["se muestra el mismo resultado"],
        body="When el usuario selecciona la opción\nThen se muestra el mismo resultado",
        extra_test_data="tipo=B",
        scenario="se muestra el mismo resultado",
    )
    drafts = compose_story_units([a, b])
    assert len(drafts) == 1
    assert len(drafts[0].steps) == 1
    assert drafts[0].steps[0].covered_unit_ids == ["COV-001", "COV-002"]


def test_validator_fills_missing_executable_units() -> None:
    unit = _unit(
        body="When el usuario abre el detalle\nThen se muestra el detalle",
        user_action="el usuario abre el detalle",
        observable_then=["se muestra el detalle"],
        scenario="se muestra el detalle",
    )
    filled: list = []

    def _fill(missing):
        filled.extend(missing)
        return compose_inventory(missing, [], lambda *_a: None)

    validate_composed_candidates([], [unit], fill_missing=_fill)
    assert filled and filled[0].coverage_id == "COV-001"


def test_phrases_similar_is_structural() -> None:
    assert phrases_similar("se muestra el menú de opciones", "Given se muestra el menú de opciones")
    assert not phrases_similar("se muestra el menú", "se oculta el error de red")
