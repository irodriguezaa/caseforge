"""FASE 6C: writing standard on composed flows. Synthetic Gherkin only."""

from app.schemas.case_generation import CoverageUnit
from app.services.case_composer import compose_inventory, compose_story_units
from app.services.gherkin_coverage import candidates_from_jira_artifacts


def _artifacts(description: str) -> list[dict]:
    return [
        {
            "key": "EPC-1",
            "issuetype": "Technical Epic",
            "children": [
                {
                    "key": "ST-1",
                    "issuetype": "Technical Story",
                    "summary": "Feature flujo",
                    "description": description,
                    "acceptance_criteria": "",
                }
            ],
        }
    ]


def test_c1_does_not_dump_quoted_epic_literals_into_test_data() -> None:
    description = """
Scenario: Confirmar el alta
  When el usuario selecciona "Guardar ficha"
  Then se muestra "Ficha guardada"
"""
    epic = {
        "key": "EPC-1",
        "issuetype": "Technical Epic",
        "description": 'La épica menciona "Panel lateral" y "id-9" y un smartlink mention',
        "children": _artifacts(description)[0]["children"],
    }
    cases = candidates_from_jira_artifacts([epic], "rn.pdf", [], lambda *_a: None)
    assert cases
    data = " ".join(row.test_data or "" for row in cases)
    assert "id-9" not in data
    assert "smartlink" not in data.lower()
    assert "mention" not in data.lower()
    assert "Panel lateral" not in data


def test_c2_state_given_is_precondition_not_step() -> None:
    description = """
Scenario: Abrir el detalle
  Given el usuario está autenticado
  And se encuentra en la pantalla principal
  When el usuario abre el detalle
  Then se muestra el detalle
"""
    cases = candidates_from_jira_artifacts(_artifacts(description), "rn.pdf", [], lambda *_a: None)
    actions = " ".join(step.action.lower() for row in cases for step in row.steps)
    assert "autenticado" not in actions
    assert "se encuentra" not in actions
    assert any("abrir" in step.action.lower() or "abre" in step.action.lower() for row in cases for step in row.steps)


def test_c2_system_when_attaches_to_previous_or_navigates() -> None:
    description = """
Scenario: El usuario abre el resumen
  When el usuario abre el resumen
  Then se muestra el resumen
Scenario: El sistema actualiza el total
  When el sistema recalcula el total
  Then se muestra el total actualizado
"""
    cases = candidates_from_jira_artifacts(_artifacts(description), "rn.pdf", [], lambda *_a: None)
    assert cases
    actions = [step.action for row in cases for step in row.steps]
    assert any(actions)
    assert all(step.action for row in cases for step in row.steps) or any(
        "pendiente" in " ".join(row.applied_rules or []) for row in cases
    )


def test_c3_strips_endpoint_and_key_from_expected() -> None:
    description = """
Scenario: Ver el estado
  When el usuario abre el estado
  Then el servicio GET /services/cms/v2/level responde 200 y StatusCode: "200" y NombreDeLlave: LISTO
"""
    cases = candidates_from_jira_artifacts(_artifacts(description), "rn.pdf", [], lambda *_a: None)
    expected = " ".join(step.expected_result for row in cases for step in row.steps)
    assert "GET" not in expected
    assert "/services/" not in expected
    assert "NombreDeLlave" not in expected


def test_c3_splits_exclusive_negative_and_positive() -> None:
    description = """
Scenario: Confirmar el código
  When el usuario ingresa el código
  Then se muestra el tooltip de código inválido
  And el código fue ingresado correctamente
"""
    drafts = compose_story_units(
        [
            CoverageUnit(
                coverage_id="COV-1",
                role="G",
                behavior="código",
                scenario="Confirmar el código",
                evidence="e",
                body=(
                    "When el usuario ingresa el código\n"
                    "Then se muestra el tooltip de código inválido\n"
                    "And el código fue ingresado correctamente"
                ),
                user_action="el usuario ingresa el código",
                observable_then=[
                    "se muestra el tooltip de código inválido",
                    "el código fue ingresado correctamente",
                ],
                story_key="ST-1",
                artifact_key="EPC-1",
            )
        ]
    )
    assert drafts and len(drafts[0].steps) >= 2
    joined = " | ".join(f"{step.action} -> {step.expected_result}" for step in drafts[0].steps)
    assert "inválid" in joined.lower()
    assert "correctamente" in joined.lower()


def test_c4_same_expected_different_intent_stays_separate() -> None:
    description = """
Scenario: Guardar
  When el usuario selecciona Guardar
  Then se muestra la confirmación
Scenario: Descartar
  When el usuario selecciona Descartar
  Then se muestra la confirmación
"""
    cases = candidates_from_jira_artifacts(_artifacts(description), "rn.pdf", [], lambda *_a: None)
    assert len(cases) >= 2
    actions = " ".join(step.action.lower() for row in cases for step in row.steps)
    assert "guardar" in actions
    assert "descartar" in actions


def test_c5_na_units_are_not_mixed_into_executable() -> None:
    exe = CoverageUnit(
        coverage_id="COV-E",
        role="G",
        behavior="ok",
        scenario="ok",
        evidence="e",
        body="When el usuario abre el panel\nThen se muestra el panel",
        user_action="el usuario abre el panel",
        observable_then=["se muestra el panel"],
        story_key="ST-1",
        artifact_key="EPC-1",
        applicability="ejecutable",
    )
    na = CoverageUnit(
        coverage_id="COV-N",
        role="G",
        behavior="remoto",
        scenario="remoto",
        evidence="e",
        body="When el backend no responde\nThen no hay datos",
        story_key="ST-1",
        artifact_key="EPC-1",
        applicability="na_ambiente",
        applicability_reason="na_ambiente:sin ambiente",
    )
    out = compose_inventory([exe, na], [], lambda *_a: None)
    na_cases = [row for row in out if row.applicability == "na_ambiente"]
    exe_cases = [row for row in out if row.applicability != "na_ambiente"]
    assert na_cases
    assert all("COV-N" not in (row.covers or []) for row in exe_cases)
    assert all("COV-E" not in (row.covers or []) for row in na_cases)


def test_c6_title_is_short_without_feature_dump() -> None:
    description = """
Scenario: Validar: se muestra el resultado
  When el usuario selecciona Continuar
  Then se muestra el resultado
"""
    cases = candidates_from_jira_artifacts(_artifacts(description), "rn.pdf", [], lambda *_a: None)
    assert cases
    assert all(len(row.name) <= 120 for row in cases)
    assert all("Feature" not in (row.name or "") for row in cases)
    assert all(" — " not in (row.name or "") for row in cases)
