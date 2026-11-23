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


def test_title_comes_from_the_scenario_not_the_steps():
    rebuilt = clean_title('Alta del método "', "Usuario externo", "Seleccionar alta", "Se muestra el formulario")
    assert rebuilt == "Alta del método"
    assert "Seleccionar" not in rebuilt


def test_externalregister_matches_the_glossary_without_underscores():
    text, warnings = gloss_precondition("source = EXTERNALREGISTER")
    assert text == "Usuario externo que se acaba de registrar"
    assert warnings == []


def test_unknown_user_type_is_kept_and_warned():
    text, warnings = gloss_precondition("El usuario es EXTERNAL_FOO_REGISTER")
    assert text and "EXTERNAL_FOO_REGISTER" in text
    assert warnings


def test_then_sequence_is_kept_and_there_is_no_filler():
    unit = _unit(
        "c1",
        "HN-1",
        "Confirmar el pago con PIN",
        "\n".join(
            [
                "Given el usuario tiene un método de pago registrado",
                "When el usuario ingresa el PIN",
                "Then se valida el PIN",
                "And se muestra el modal de confirmación",
                "And se redirige a la pantalla de inicio",
            ]
        ),
    )
    unit.feature_background = "Given el usuario es anónimo"
    cases = compose_scenario_inventory([unit], [], lambda *_args: None)
    assert len(cases) == 1
    case = cases[0]
    assert case.name == "Confirmar el pago con PIN"
    blob = " ".join(step.expected_result or "" for step in case.steps).lower()
    assert "valida el pin" in blob
    assert "modal" in blob
    assert "redirige" in blob
    assert all((step.expected_result or "").strip() for step in case.steps)
    assert all("verificar lo que muestra" not in step.action.lower() for step in case.steps)
    assert all((step.expected_result or "").strip().lower() != "se muestra la pantalla." for step in case.steps)
    assert "anónimo" not in (case.precondition or "").lower()
    assert "método de pago" in (case.precondition or "").lower() or "metodo de pago" in (case.precondition or "").lower()


def test_epic_criterion_is_registered_and_not_a_case():
    unit = _unit(
        "e1",
        "HN-1",
        "Los mensajes se muestran de forma clara",
        "Then Los mensajes se muestran de forma clara",
    )
    unit.source_origin = "ac"
    unit.applied_rules = ["ac-epica"]
    stats = GenerationStats()
    cases = compose_scenario_inventory([unit], [], lambda *_args: None)
    assert cases == []
    fill_scenario_ledger(stats, [unit], cases)
    row = stats.scenario_ledger[0]
    assert row["estado"] == "criterio de épica – revisar"
    assert "mensajes" in row["motivo"].lower()


def test_each_action_is_followed_by_its_result():
    unit = _unit(
        "d1",
        "HN-1",
        "Eliminar con suscripciones",
        "\n".join(
            [
                'When el usuario selecciona el botón "Eliminar"',
                "Then se muestra el modal de confirmación",
                'When el usuario selecciona el botón "Cancelar"',
                "Then se dirige a la pantalla anterior",
            ]
        ),
    )
    cases = compose_scenario_inventory([unit], [], lambda *_args: None)
    case = cases[0]
    pairs = [(step.action, step.expected_result) for step in case.steps]
    assert pairs[0][0] == "Seleccionar el botón «Eliminar»"
    assert "modal" in pairs[0][1].lower()
    assert pairs[1][0] == "Seleccionar el botón «Cancelar»"
    assert "pantalla anterior" in pairs[1][1].lower()
    assert "se muestra eliminar" not in pairs[0][1].lower()


def test_priority_bands():
    assert classify_legacy_priority("Alta de método de pago", "seleccionar alta") == "BLOCKER"
    assert classify_legacy_priority("Error al ocultar el botón", "no se muestra el botón") == "CRITICAL"
    assert classify_legacy_priority("Texto del banner en la home", "el texto usa la tipografía") == "MAJOR"
