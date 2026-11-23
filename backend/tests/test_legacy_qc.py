"""Reglas generales del motor legacy. Sin tickets ni EPCs reales."""

from app.schemas.case_generation import CoverageUnit, GenerationStats
from app.services.legacy_qc import (
    classify_legacy_priority,
    clean_title,
    given_goes_to_step,
    gloss_precondition,
    legacy_disposition,
)
from app.services.scenario_cases import compose_scenario_inventory, fill_scenario_ledger


def _unit(
    coverage_id: str,
    story: str,
    scenario: str,
    body: str,
    epic: str = "EPC-1",
) -> CoverageUnit:
    return CoverageUnit(
        coverage_id=coverage_id,
        role="A",
        behavior=scenario,
        scenario=scenario,
        evidence=f"{story}\n{body}",
        jira_key=story,
        artifact_key=epic,
        story_key=story,
        body=body,
        story_summary=scenario,
    )


def test_glossary_translates_and_drops_unknown_api():
    text, warnings = gloss_precondition("El usuario es EXTERNAL_REGISTER")
    assert text == "Usuario externo que se acaba de registrar"
    assert warnings == []
    dropped, warnings = gloss_precondition("La API /services/user responde 200")
    assert dropped is None
    assert warnings


def test_given_action_is_not_a_precondition():
    assert given_goes_to_step("el usuario busca una película")
    assert given_goes_to_step("iniciar sesión con el correo")
    assert not given_goes_to_step("el usuario tiene sesión iniciada")


def test_key_and_api_then_are_not_cases_and_no_change_is_regression():
    kind, _ = legacy_disposition("No se logra obtener una llave", "Then no llega la llave")
    assert kind == "verificacion"
    kind, _ = legacy_disposition(
        "Consulta de hash",
        "Then se obtiene el user_hash del endpoint",
    )
    assert kind == "verificacion"
    kind, _ = legacy_disposition(
        "La home se ve igual que antes",
        "Then la home se ve igual que antes",
    )
    assert kind == "regresion"


def test_visible_then_with_an_api_clause_stays_a_case():
    kind, _ = legacy_disposition(
        "Alta exitosa del método de pago",
        "Then se muestra el modal de alta\nAnd se llama a la API de registro",
    )
    assert kind == "caso"


def test_different_stories_do_not_merge_when_the_result_differs():
    alta = _unit(
        "c1",
        "HN-1",
        "Alta exitosa del método de pago",
        "Given el usuario tiene sesión\nWhen selecciona agregar método\nThen se muestra el formulario de alta",
    )
    borrar = _unit(
        "c2",
        "HN-2",
        "Eliminar el método de pago sin suscripciones",
        "Given el usuario tiene sesión\nWhen selecciona eliminar\nThen se elimina el método de pago",
    )
    cases = compose_scenario_inventory([alta, borrar], [], lambda *_args: None)
    names = " ".join(case.name for case in cases).lower()
    assert len(cases) == 2
    assert "eliminar" not in cases[0].name.lower() or "alta" not in cases[0].name.lower()
    joined_steps = " ".join(step.action for case in cases for step in case.steps).lower()
    alta_case = next(case for case in cases if "alta" in case.name.lower())
    assert "eliminar" not in " ".join(step.action for step in alta_case.steps).lower()
    assert "eliminar" in joined_steps
    assert names


def test_same_scenario_across_stories_becomes_variants():
    body = "Given el usuario tiene sesión\nWhen busca un título\nThen se muestra el resultado de la búsqueda"
    anon = _unit("a", "HN-1", "Buscar un título en el catálogo", body)
    anon.story_summary = "Usuario anónimo"
    logged = _unit("b", "HN-2", "Buscar un título en el catálogo", body)
    logged.story_summary = "Usuario con sesión"
    cases = compose_scenario_inventory([anon, logged], [], lambda *_args: None)
    assert len(cases) == 1
    assert "Usuario anónimo" in (cases[0].variant_table or "")
    assert "Usuario con sesión" in (cases[0].variant_table or "")


def test_action_given_becomes_a_step_and_api_leaves_the_precondition():
    unit = _unit(
        "c1",
        "HN-1",
        "Registro de un usuario externo en la home",
        "\n".join(
            [
                "Given el usuario es EXTERNAL_REGISTER",
                "And busca el contenido destacado",
                "And la API /services/apa/metadata responde 200",
                "When selecciona reproducir",
                "Then se muestra el player",
            ]
        ),
    )
    stats = GenerationStats()
    cases = compose_scenario_inventory([unit], [], lambda *_args: None)
    fill_scenario_ledger(stats, [unit], cases)
    assert len(cases) == 1
    actions = [step.action.lower() for step in cases[0].steps]
    assert any("busca" in action or "buscar" in action for action in actions)
    assert any("reproduc" in action or "seleccion" in action for action in actions)
    assert len(cases[0].steps) >= 2
    pre = (cases[0].precondition or "").lower()
    assert "api" not in pre
    assert "/services/" not in pre
    assert "externo" in pre
    assert any("advertencia" in (row.get("motivo") or "") for row in stats.scenario_ledger)


def test_title_rebuilds_when_the_scenario_name_is_cut_off():
    rebuilt = clean_title('Alta del método "', "Usuario externo", "Seleccionar alta", "Se muestra el formulario")
    assert len(rebuilt.split()) >= 4
    assert '"' not in rebuilt


def test_priority_bands():
    assert classify_legacy_priority("Alta de método de pago", "seleccionar alta") == "BLOCKER"
    assert classify_legacy_priority("Error al ocultar el botón", "no se muestra el botón") == "CRITICAL"
    assert classify_legacy_priority("Texto del banner en la home", "el texto usa la tipografía") == "MAJOR"
