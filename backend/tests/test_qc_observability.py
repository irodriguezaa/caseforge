"""QC observability is a second decision: A–G does not auto-discard functional Then."""

from app.services.executability import STABLE_GENERIC_STEP
from app.services.gherkin_coverage import (
    build_coverage_inventory,
    candidates_from_jira_artifacts,
    parse_gherkin_blocks,
)
from app.services.qc_observability import classify_qc_observability, translate_then_to_observable
from app.services.scenario_classifier import classify_scenario


def _story(key: str, description: str, epic: str = "EPIC-QC") -> list[dict]:
    return [
        {
            "key": epic,
            "issuetype": "Technical Epic",
            "summary": epic,
            "description": "",
            "children": [
                {
                    "key": key,
                    "issuetype": "Technical Story",
                    "summary": key,
                    "description": description,
                    "acceptance_criteria": "",
                }
            ],
        }
    ]


def test_renderiza_with_named_surface_is_qc_candidate() -> None:
    clf = classify_scenario(
        "Home sin componente comercial",
        "Given el nodo no es de primer nivel\n"
        "Then no se renderiza el Background comercial\n"
        "And el Brandheader conserva su comportamiento actual\n",
    )
    assert clf.role == "C"
    assert clf.qc_relevance == "QC_REGRESSION"
    assert any("background" in item.lower() for item in clf.qc_observables)
    units = build_coverage_inventory(
        _story(
            "STORY-R",
            "Scenario: Home sin componente comercial\n"
            "  Given el nodo no es de primer nivel\n"
            "  Then no se renderiza el Background comercial\n"
            "  And el Brandheader conserva su comportamiento actual\n",
        ),
        "rn.pdf",
    )
    assert [unit.scenario for unit in units] == ["Home sin componente comercial"]
    assert units[0].role == "G"


def test_oculta_with_named_surface_is_qc_candidate() -> None:
    clf = classify_scenario(
        "Se oculta el encabezado",
        "Then se oculta el Brandheader\n",
    )
    assert clf.role == "C"
    assert clf.qc_relevance in {"QC_FUNCTIONAL", "QC_REGRESSION"}
    mapped = translate_then_to_observable("se oculta el Brandheader")
    assert mapped and "brandheader" in mapped.lower()


def test_habilita_renderizado_is_qc_candidate() -> None:
    clf = classify_scenario(
        "Activa el fondo comercial",
        "Given el nodo es de primer nivel\n"
        "Then se habilita el renderizado del Background comercial\n"
        "And se oculta el Brandheader\n",
    )
    assert clf.role == "C"
    assert clf.qc_relevance == "QC_FUNCTIONAL"
    units = build_coverage_inventory(
        _story(
            "STORY-H",
            "Scenario: Activa el fondo comercial\n"
            "  Given el nodo es de primer nivel\n"
            "  Then se habilita el renderizado del Background comercial\n"
            "  And se oculta el Brandheader\n",
        ),
        "rn.pdf",
    )
    assert len(units) == 1
    assert units[0].observable_then


def test_scroll_plus_observable_change_is_qc_candidate() -> None:
    clf = classify_scenario(
        "Transicion al hacer scroll hacia abajo",
        "When el usuario hace scroll hacia abajo y supera el umbral\n"
        "Then el gradient transiciona progresivamente de estado inicial a estado solido con blur\n",
    )
    assert clf.role == "C"
    assert clf.qc_relevance in {"QC_FUNCTIONAL", "QC_REGRESSION"}
    assert clf.qc_user_action
    assert "scroll" in (clf.qc_user_action or "").lower()
    units = build_coverage_inventory(
        _story(
            "STORY-S",
            "Scenario: Transicion al hacer scroll hacia abajo\n"
            "  When el usuario hace scroll hacia abajo y supera el umbral\n"
            "  Then el gradient transiciona progresivamente de estado inicial a estado solido\n"
            "Scenario: Retorno al hacer scroll hacia arriba\n"
            "  When el usuario hace scroll hacia arriba por encima del umbral\n"
            "  Then el gradient regresa a su estado inicial\n",
        ),
        "rn.pdf",
    )
    assert len(units) == 1
    blob = f"{units[0].scenario} {units[0].extra_test_data or ''} {units[0].behavior}"
    assert "scroll" in blob.lower()


def test_config_without_observable_is_config_only() -> None:
    clf = classify_scenario(
        "Region sin configuracion propia",
        'Then se aplica el valor de "enabled" del objeto "default"\n',
    )
    assert clf.qc_relevance == "CONFIG_ONLY"
    units = build_coverage_inventory(
        _story(
            "STORY-CFG",
            'Scenario: Region sin configuracion propia\n'
            '  Then se aplica el valor de "enabled" del objeto "default"\n',
        ),
        "rn.pdf",
    )
    assert units == []


def test_config_plus_observable_behavior_is_qc_candidate() -> None:
    clf = classify_scenario(
        "Funcionalidad deshabilitada",
        "Given enabled resuelve en false para la region\n"
        "Then no se renderiza el Background comercial en ninguna condicion\n"
        "And el Brandheader conserva su comportamiento actual\n",
    )
    assert clf.role == "C"
    assert clf.qc_relevance in {"QC_FUNCTIONAL", "QC_REGRESSION"}
    units = build_coverage_inventory(
        _story(
            "STORY-FLAG",
            "Scenario: Funcionalidad deshabilitada\n"
            "  Given enabled resuelve en false para la region\n"
            "  Then no se renderiza el Background comercial en ninguna condicion\n"
            "  And el Brandheader conserva su comportamiento actual\n",
        ),
        "rn.pdf",
    )
    assert len(units) == 1


def test_key_construction_is_implementation_only() -> None:
    clf = classify_scenario(
        "Construccion de la llave del asset",
        'Given el Home se carga con el query param "node" igual a "homeuser"\n'
        'Then la llave resuelta es "background_imagen_fondo_homeuser"\n'
        "And ninguna URL de asset queda hardcodeada en la aplicacion\n",
    )
    assert clf.qc_relevance == "IMPLEMENTATION_ONLY"
    units = build_coverage_inventory(
        _story(
            "STORY-KEY",
            "Scenario: Construccion de la llave del asset\n"
            '  Then la llave resuelta es "background_imagen_fondo_homeuser"\n'
            "  And ninguna URL de asset queda hardcodeada en la aplicacion\n",
        ),
        "rn.pdf",
    )
    assert units == []


def test_definition_variant_is_not_independent_tc() -> None:
    clf = classify_scenario(
        "Solo una de las dos condiciones se cumple",
        "Given un componente tiene type Highlight pero properties.type distinto de simple\n"
        "Then se considera que NO existe Super Destacado\n",
    )
    assert clf.qc_relevance == "QC_VARIANT"
    description = (
        "Scenario: Nodo de primer nivel sin Super Destacado\n"
        "  Then se habilita el renderizado del Background comercial\n"
        "  And se oculta el Brandheader\n"
        "Scenario: Solo una de las dos condiciones se cumple\n"
        "  Then se considera que NO existe Super Destacado\n"
    )
    units = build_coverage_inventory(_story("STORY-V", description), "rn.pdf")
    scenarios = [unit.scenario for unit in units]
    assert "Nodo de primer nivel sin Super Destacado" in scenarios
    assert "Solo una de las dos condiciones se cumple" not in scenarios


def test_does_not_invent_unsupported_user_action() -> None:
    clf = classify_scenario(
        "Home sin componente comercial",
        "Given el nodo no es de primer nivel\n"
        "Then no se renderiza el Background comercial\n",
    )
    assert clf.qc_user_action in {None, STABLE_GENERIC_STEP}
    assert "recorre la experiencia" not in (clf.qc_user_action or "").lower()
    obs = classify_qc_observability(
        "Home sin componente comercial",
        "Then no se renderiza el Background comercial\n",
        role="C",
        then=["no se renderiza el Background comercial"],
    )
    assert obs.user_action in {None, STABLE_GENERIC_STEP}


def test_traceability_epic_story_scenario_unit_tc() -> None:
    artifacts = _story(
        "STORY-T",
        "Scenario: Activa el fondo comercial\n"
        "  Then se habilita el renderizado del Background comercial\n"
        "  And se oculta el Brandheader\n",
        epic="EPIC-T",
    )
    units = build_coverage_inventory(artifacts, "rn.pdf")
    assert len(units) == 1
    unit = units[0]
    assert unit.rn_key == "EPIC-T"
    assert unit.story_key == "STORY-T"
    assert unit.scenario == "Activa el fondo comercial"
    assert unit.coverage_id.startswith("COV-")
    assert "EPIC-T" in unit.traceability and "STORY-T" in unit.traceability
    cases = candidates_from_jira_artifacts(artifacts, "rn.pdf", [], lambda *_args: None)
    assert len(cases) == 1
    assert cases[0].related_functionality == "EPIC-T"
    assert cases[0].related_jira == "STORY-T"
    assert unit.coverage_id in (cases[0].covers or [])
    blob = " ".join(step.action for step in cases[0].steps)
    assert "recorre la experiencia cuando" not in blob.lower()


def test_generic_then_with_given_table_is_qc_functional() -> None:
    body = (
        "Given se muestra pantalla Post Reproducción con formato visual tipo PIP\n"
        "And el comportamiento del RCU es el siguiente:\n"
        "| Elemento | Acción |\n"
        "| Botón OK | Seleccionar ventana con formato visual tipo PIP |\n"
        "| Botón Back | Se oculta la pantalla de Post Reproducción y continua la reproducción de créditos en pantalla completa |\n"
        "Then el comportamiento debe cumplir con las especificaciones solicitadas por el equipo de negocio\n"
    )
    clf = classify_scenario("Seleccionar la ventana PIP desde el RCU", body)
    assert clf.qc_relevance == "QC_FUNCTIONAL"
    assert clf.observable_then
    assert any("oculta" in item.lower() or "pip" in item.lower() or "seleccionar" in item.lower() for item in clf.observable_then)


def test_se_muestra_is_observable() -> None:
    mapped = translate_then_to_observable("se muestra la Pantalla Post Reproducción")
    assert mapped
    clf = classify_scenario("PIP visible", 'Then se muestra la Pantalla "Post Reproducción"\n')
    assert clf.observable_then or clf.qc_observables


def test_rcu_action_plus_result_is_qc_functional() -> None:
    clf = classify_scenario(
        "Navegacion RCU del PIP",
        "Given el usuario se encuentra en Post Reproducción\n"
        "| Flecha de navegación hacia arriba (↑) | La posición debe cambiar al siguiente elemento disponible |\n"
        "| Botón Back | Se oculta la pantalla de Post Reproducción |\n"
        "Then el comportamiento debe cumplir con las especificaciones\n",
    )
    assert clf.qc_relevance == "QC_FUNCTIONAL"
    units = build_coverage_inventory(
        _story(
            "STORY-RCU",
            "Scenario: Navegacion RCU del PIP\n"
            "  Given el usuario se encuentra en Post Reproducción\n"
            "  | Flecha de navegación hacia arriba (↑) | La posición debe cambiar al siguiente elemento disponible |\n"
            "  | Botón Back | Se oculta la pantalla de Post Reproducción |\n"
            "  Then el comportamiento debe cumplir con las especificaciones\n",
        ),
        "rn.pdf",
    )
    assert len(units) == 1
    assert units[0].scenario == "Navegacion RCU del PIP"


def test_key_token_with_functional_then_is_not_discarded() -> None:
    clf = classify_scenario(
        "No se logra obtener una llave",
        "Given una llave no se encuentra en apa/metadata\n"
        "When la aplicación intenta construir la leyenda\n"
        "Then el espacio donde debería mostrarse la leyenda debe mostrar la llave\n"
        "And no debe mostrarse un texto de error visible para el usuario\n",
    )
    assert clf.qc_relevance == "QC_VARIANT"
    assert clf.observable_then
    units = build_coverage_inventory(
        _story(
            "STORY-KEY-OBS",
            "Scenario: No se logra obtener una llave\n"
            "  Given una llave no se encuentra en apa/metadata\n"
            "  Then el espacio donde debería mostrarse la leyenda debe mostrar la llave\n"
            "  And no debe mostrarse un texto de error visible para el usuario\n"
            "Scenario: La llave se encuentra vacia\n"
            "  Given una llave esta vacia en apa/metadata\n"
            "  Then el espacio donde debería mostrarse la leyenda debe quedar vacía\n"
            "  And no debe mostrarse un texto de error visible para el usuario\n",
        ),
        "rn.pdf",
    )
    scenarios = [unit.scenario for unit in units]
    assert "No se logra obtener una llave" in scenarios
    assert "La llave se encuentra vacia" in scenarios
    assert len(units) == 2


def test_does_not_turn_every_scenario_into_a_tc() -> None:
    units = build_coverage_inventory(
        _story(
            "STORY-GRP",
            "Scenario: Transicion al hacer scroll hacia abajo\n"
            "  When el usuario hace scroll hacia abajo y supera el umbral\n"
            "  Then el gradient transiciona progresivamente de estado inicial a estado solido\n"
            "Scenario: Retorno al hacer scroll hacia arriba\n"
            "  When el usuario hace scroll hacia arriba por encima del umbral\n"
            "  Then el gradient regresa a su estado inicial\n",
        ),
        "rn.pdf",
    )
    assert len(units) == 1


STVCL_332 = """Feature: Implementar ventana con formato visual tipo PIP de créditos
  Scenario: Ventana con formato visual tipo PIP en la pantalla de Post Reproducción
    Given el usuario se encuentra en la pantalla de Post Reproducción con formato visual tipo PIP
    Then se muestra la Pantalla "Post Reproducción con formato visual tipo PIP" con los elementos:
    | Elementos | Descripción |
    | Ventana con formato PIP | Ventana reducida del contenido reproducido |
    | Botón Cerrar con foco | Botón Cerrar |

  Scenario: Seleccionar la ventana con formato visual tipo PIP desde el RCU
    Given se muestra pantalla Post Reproducción con formato visual tipo PIP
    And el comportamiento del RCU es el siguiente:
    | Elemento | Acción |
    | Botón OK | Seleccionar ventana con formato visual tipo PIP |
    | Botón Back | Se oculta la pantalla de Post Reproducción y Continua la reproducción de los créditos en pantalla completa |
    Then el comportamiento debe cumplir con las especificaciones solicitadas por el equipo de negocio

  Scenario: Comportamiento de la vista del reproductor con formato visual tipo PIP
    Given se muestra pantalla Post Reproducción con formato visual tipo PIP
    And el comportamiento de la vista del reproductor es el siguiente:
    * La vista del reproductor con formato visual tipo PIP debe reproducir de manera continua los créditos del contenido VOD aun cuando no se tenga en foco.
    * Cuando la vista del reproductor se encuentre en foco, se debe visualizar un outline.
    * Cuando el usuario seleccione la vista del reproductor, se debe de ocultar la pantalla de Calificación y se debe volver a pantalla completa la reproducción de los créditos junto con el Fin player.
    Then el comportamiento debe cumplir con las especificaciones solicitadas por el equipo de negocio

  Scenario: No se logra obtener una llave
    Given una llave que construye la pantalla no se encuentra en el response de la API "apa/metadata"
    When la aplicación intenta construir la leyenda
    Then el espacio donde debería mostrarse la leyenda debe mostrarse la llave
    And no debe mostrarse un texto de error visible para el usuario

  Scenario: La llave se encuentra vacia
    Given una llave que construye la pantalla esta vacia en el response de la API "apa/metadata"
    When la aplicación intenta construir la leyenda
    Then el espacio donde debería mostrarse la leyenda debe quedar vacía
    And no debe mostrarse un texto de error visible para el usuario
"""


def test_stvcl332_recovers_four_functional_behaviors_without_one_to_one_tcs() -> None:
    artifacts = _story("STVCL-332", STVCL_332, epic="STVCL-286")
    units = build_coverage_inventory(artifacts, "rn.pdf")
    scenarios = {unit.scenario for unit in units}
    assert "Ventana con formato visual tipo PIP en la pantalla de Post Reproducción" in scenarios
    assert "Seleccionar la ventana con formato visual tipo PIP desde el RCU" in scenarios
    assert "Comportamiento de la vista del reproductor con formato visual tipo PIP" in scenarios
    assert "No se logra obtener una llave" in scenarios
    assert "La llave se encuentra vacia" in scenarios
    assert 4 <= len(units) <= 6
    cases = candidates_from_jira_artifacts(artifacts, "rn.pdf", [], lambda *_args: None)
    assert len(cases) == len(units)
    assert len(cases) <= 6
    for unit in units:
        assert "STVCL-286" in unit.traceability
        assert "STVCL-332" in unit.traceability
        assert unit.observable_then


def test_generic_then_with_when_ui_layout_is_qc_functional() -> None:
    body = (
        "Given el usuario se encuentra en Post Reproducción\n"
        "When se muestra la pantalla de calificacion con los elementos:\n"
        "| Elementos | Descripción |\n"
        "| Reproductor con formato visual tipo PIP | Vista reducida |\n"
        "| Contador del tiempo | Cuenta regresiva |\n"
        "| Botón Me gusta | Pulgar arriba |\n"
        "| Botón Me encanta | Dos pulgares |\n"
        "| Botón No me gusta | Pulgar abajo |\n"
        "| Botón Cerrar | Icono X |\n"
        "Then la pantalla debe cumplir con las especificaciones solicitadas en los insumos de diseño.\n"
    )
    clf = classify_scenario("Creación de Pantalla PIP", body)
    assert clf.qc_relevance == "QC_FUNCTIONAL"
    blob = " ".join(clf.observable_then or []).lower()
    assert "pip" in blob or "pantalla" in blob or "botón" in blob or "boton" in blob
    units = build_coverage_inventory(
        _story("STORY-LAY", f"Scenario: Creación de Pantalla PIP\n{body}"),
        "rn.pdf",
    )
    assert len(units) == 1
    assert units[0].scenario == "Creación de Pantalla PIP"


def test_generic_then_does_not_treat_user_action_when_as_result() -> None:
    clf = classify_scenario(
        "El usuario activa",
        "When el usuario selecciona Activar ahora\n"
        "Then el comportamiento debe cumplir con las especificaciones\n",
    )
    assert clf.qc_relevance != "QC_FUNCTIONAL"
    assert not any("activar ahora" in (item or "").lower() for item in (clf.observable_then or []))


def test_examples_plural_parses_rows() -> None:
    blocks = parse_gherkin_blocks(
        "Scenario Outline: Calificación de Contenido\n"
        "  When el usuario selecciona un botón para calificar\n"
        "  Then se muestra la botonera de Calificación\n"
        "  Examples:\n"
        "    | Calificación | Descripción |\n"
        "    | -1 | No me gusta |\n"
        "    | 1 | Me gusta |\n"
        "    | 2 | Me encanta |\n"
    )
    assert len(blocks) == 1
    assert len(blocks[0]["examples"]) == 3


def test_example_singular_parses_rows() -> None:
    blocks = parse_gherkin_blocks(
        "Scenario Outline: Calificación de Contenido\n"
        "  When el usuario selecciona un botón para calificar\n"
        "  Then se muestra la botonera de Calificación\n"
        "  Example:\n"
        "    | <Calificación> | Descripción |\n"
        "    | -1 | No me gusta |\n"
        "    | 1 | Me gusta |\n"
        "    | 2 | Me encanta |\n"
    )
    assert len(blocks) == 1
    assert len(blocks[0]["examples"]) == 3
    values = {
        (row.get("<Calificación>") or row.get("Calificación") or "").strip()
        for row in blocks[0]["examples"]
    }
    assert values == {"-1", "1", "2"}


def test_rating_outline_is_one_unit_with_three_variants() -> None:
    description = (
        "Scenario Outline: Calificación de Contenido\n"
        "  Given el usuario se encuentra en la pantalla de calificación\n"
        "  And se muestra la botonera de Calificación\n"
        "  When el usuario selecciona un botón para calificar\n"
        "  Then el contenido fue calificado por el usuario correctamente\n"
        "  And se muestra la botonera de Calificación\n"
        "  Example:\n"
        "    | <Calificación> | Descripción |\n"
        "    | -1 | No me gusta |\n"
        "    | 1 | Me gusta |\n"
        "    | 2 | Me encanta |\n"
    )
    units = build_coverage_inventory(_story("STVCL-334", description, epic="STVCL-333"), "rn.pdf")
    assert len(units) == 1
    extra = (units[0].extra_test_data or "").lower()
    assert "-1" in extra and "1" in extra and "2" in extra
    assert "no me gusta" in extra and "me gusta" in extra and "me encanta" in extra
    cases = candidates_from_jira_artifacts(
        _story("STVCL-334", description, epic="STVCL-333"),
        "rn.pdf",
        [],
        lambda *_args: None,
    )
    assert len(cases) == 1


def test_notificacion_se_debe_ocultar_is_qc_functional() -> None:
    clf = classify_scenario(
        "Alerta de Notificación de calificación previa",
        "Given el usuario realiza una nueva calificación del contenido\n"
        "When la notificación de la calificación anterior aún se muestra en pantalla\n"
        "Then la notificación se debe ocultar\n",
    )
    assert clf.qc_relevance == "QC_FUNCTIONAL"
    assert clf.observable_then


def test_notificacion_debe_ocultarse_is_qc_functional() -> None:
    clf = classify_scenario(
        "Alerta de Notificación",
        "Then la notificación debe ocultarse\n",
    )
    assert clf.qc_relevance == "QC_FUNCTIONAL"
    mapped = translate_then_to_observable("la notificación debe ocultarse")
    assert mapped


def test_notificacion_se_oculta_is_qc_functional() -> None:
    clf = classify_scenario(
        "Alerta de Notificación",
        "Then la notificación se oculta\n",
    )
    assert clf.qc_relevance == "QC_FUNCTIONAL"


def test_rules_for_timeouts_do_not_create_independent_tc() -> None:
    description = """Feature: Calificación
  Rule: El tiempo máximo para cerrar la pantalla es de 60 segundos (max_display_time).
  Rule: display_time 30 segundos si el usuario no interactúa.
  Rule: post_vote_display_time 10 segundos tras una calificación.

    [Llave]
      vod_rating_settings
      | enable | true |
      | display_time | 30 |
      | post_vote_display_time | 10 |
      | max_display_time | 60 |
"""
    units = build_coverage_inventory(_story("STORY-RULE", description), "rn.pdf")
    assert units == []
    cases = candidates_from_jira_artifacts(
        _story("STORY-RULE", description), "rn.pdf", [], lambda *_args: None
    )
    assert cases == []


WEBCL_4142 = """Feature: Scroll del header
  Scenario: Transicion al hacer scroll hacia abajo
    When el usuario hace scroll hacia abajo y supera el umbral
    Then el gradient transiciona progresivamente de estado inicial a estado solido con blur
  Scenario: Retorno al hacer scroll hacia arriba
    When el usuario hace scroll hacia arriba por encima del umbral
    Then el gradient regresa a su estado inicial
"""


def test_webcl4142_scroll_stays_one_unit() -> None:
    artifacts = _story("WEBCL-4144", WEBCL_4142, epic="WEBCL-4142")
    units = build_coverage_inventory(artifacts, "rn.pdf")
    assert len(units) == 1
    cases = candidates_from_jira_artifacts(artifacts, "rn.pdf", [], lambda *_args: None)
    assert len(cases) == 1
    assert "scroll" in f"{units[0].scenario} {units[0].extra_test_data or ''}".lower()


STVCL_333_334 = """Feature: Funcionalidad del Módulo de Calificación
  Rule: Si rollingcreditstime tiene un valor igual a 0 continuar con FinPlayer.
  Rule: display_time 30, post_vote_display_time 10, max_display_time 60.

  Scenario: Creación de Pantalla de Calificacíon Post Reproducción con formato visual tipo PIP
    Given el usuario se encuentra en la pantalla de Post Reproducción con formato visual tipo PIP
    When se muestra la pantalla de calificacion "Post Reproducción con formato visual tipo PIP" con los elementos:
      | Elementos | Descripción |
      | Reproductor con formato visual tipo PIP | Vista reducida |
      | Contador del tiempo | Cuenta regresiva |
      | Botón Me gusta | Pulgar arriba |
      | Botón Cerrar | Icono X |
    Then la pantalla debe cumplir con las especificaciones solicitadas en los insumos de diseño.

  Scenario Outline: Calificación de Contenido
    Given el usuario se encuentra en la pantalla de calificación Post Reproducción
    And se muestra la botonera de Calificación
    When el usuario selecciona un botón para calificar
    Then el contenido fue calificado por el usuario correctamente
    And se muestra la botonera de Calificación
    Example:
      | <Calificación> | Descripción |
      | -1 | No me gusta |
      | 1 | Me gusta |
      | 2 | Me encanta |

  Scenario: Alerta de Notificación de calificación previa
    Given el usuario realiza una nueva calificación del contenido
    When la notificación de la calificación anterior aún se muestra en pantalla
    Then la notificación se debe ocultar
"""


def test_stvcl333_recovers_layout_rating_variants_and_notification() -> None:
    artifacts = _story("STVCL-334", STVCL_333_334, epic="STVCL-333")
    units = build_coverage_inventory(artifacts, "rn.pdf")
    scenarios = {unit.scenario for unit in units}
    assert any("Creación" in title for title in scenarios)
    assert any("Calificación de Contenido" in title for title in scenarios)
    assert any("Notificación" in title for title in scenarios)
    rating = next(unit for unit in units if "Calificación de Contenido" in unit.scenario)
    extra = (rating.extra_test_data or "").lower()
    assert extra.count("-1") >= 1 and "no me gusta" in extra and "me encanta" in extra
    assert not any("30" in unit.scenario and "display" in unit.scenario.lower() for unit in units)
    cases = candidates_from_jira_artifacts(artifacts, "rn.pdf", [], lambda *_args: None)
    assert len(cases) == len(units)
    assert 3 <= len(units) <= 4


def test_generic_then_with_when_ui_layout_is_qc_functional() -> None:
    body = (
        "Given el usuario se encuentra en Post Reproducción\n"
        "When se muestra la pantalla de calificacion con los elementos:\n"
        "| Elementos | Descripción |\n"
        "| Reproductor con formato visual tipo PIP | Vista reducida |\n"
        "| Contador del tiempo | Cuenta regresiva |\n"
        "| Botón Me gusta | Pulgar arriba |\n"
        "| Botón Me encanta | Dos pulgares |\n"
        "| Botón No me gusta | Pulgar abajo |\n"
        "| Botón Cerrar | Icono X |\n"
        "Then la pantalla debe cumplir con las especificaciones solicitadas en los insumos de diseño.\n"
    )
    clf = classify_scenario("Creación de Pantalla PIP", body)
    assert clf.qc_relevance == "QC_FUNCTIONAL"
    blob = " ".join(clf.observable_then or []).lower()
    assert "pip" in blob or "pantalla" in blob or "botón" in blob or "boton" in blob
    units = build_coverage_inventory(
        _story("STORY-LAY", f"Scenario: Creación de Pantalla PIP\n{body}"),
        "rn.pdf",
    )
    assert len(units) == 1
    assert units[0].scenario == "Creación de Pantalla PIP"


def test_generic_then_does_not_treat_user_action_when_as_result() -> None:
    clf = classify_scenario(
        "El usuario activa",
        "When el usuario selecciona Activar ahora\n"
        "Then el comportamiento debe cumplir con las especificaciones\n",
    )
    assert clf.qc_relevance != "QC_FUNCTIONAL"
    assert not any("activar ahora" in (item or "").lower() for item in (clf.observable_then or []))


def test_examples_plural_parses_rows() -> None:
    blocks = parse_gherkin_blocks(
        "Scenario Outline: Calificación de Contenido\n"
        "  When el usuario selecciona un botón para calificar\n"
        "  Then se muestra la botonera de Calificación\n"
        "  Examples:\n"
        "    | Calificación | Descripción |\n"
        "    | -1 | No me gusta |\n"
        "    | 1 | Me gusta |\n"
        "    | 2 | Me encanta |\n"
    )
    assert len(blocks) == 1
    assert len(blocks[0]["examples"]) == 3


def test_example_singular_parses_rows() -> None:
    blocks = parse_gherkin_blocks(
        "Scenario Outline: Calificación de Contenido\n"
        "  When el usuario selecciona un botón para calificar\n"
        "  Then se muestra la botonera de Calificación\n"
        "  Example:\n"
        "    | <Calificación> | Descripción |\n"
        "    | -1 | No me gusta |\n"
        "    | 1 | Me gusta |\n"
        "    | 2 | Me encanta |\n"
    )
    assert len(blocks) == 1
    assert len(blocks[0]["examples"]) == 3
    values = {(row.get("<Calificación>") or row.get("Calificación") or "").strip() for row in blocks[0]["examples"]}
    assert values == {"-1", "1", "2"}


def test_rating_outline_is_one_unit_with_three_variants() -> None:
    description = (
        "Scenario Outline: Calificación de Contenido\n"
        "  Given el usuario se encuentra en la pantalla de calificación\n"
        "  And se muestra la botonera de Calificación\n"
        "  When el usuario selecciona un botón para calificar\n"
        "  Then el contenido fue calificado por el usuario correctamente\n"
        "  And se muestra la botonera de Calificación\n"
        "  Example:\n"
        "    | <Calificación> | Descripción |\n"
        "    | -1 | No me gusta |\n"
        "    | 1 | Me gusta |\n"
        "    | 2 | Me encanta |\n"
    )
    units = build_coverage_inventory(_story("STVCL-334", description, epic="STVCL-333"), "rn.pdf")
    assert len(units) == 1
    extra = (units[0].extra_test_data or "").lower()
    assert "-1" in extra and "1" in extra and "2" in extra
    assert "no me gusta" in extra and "me gusta" in extra and "me encanta" in extra
    cases = candidates_from_jira_artifacts(
        _story("STVCL-334", description, epic="STVCL-333"),
        "rn.pdf",
        [],
        lambda *_args: None,
    )
    assert len(cases) == 1


def test_notificacion_se_debe_ocultar_is_qc_functional() -> None:
    clf = classify_scenario(
        "Alerta de Notificación de calificación previa",
        "Given el usuario realiza una nueva calificación del contenido\n"
        "When la notificación de la calificación anterior aún se muestra en pantalla\n"
        "Then la notificación se debe ocultar\n",
    )
    assert clf.qc_relevance == "QC_FUNCTIONAL"
    assert clf.observable_then


def test_notificacion_debe_ocultarse_is_qc_functional() -> None:
    clf = classify_scenario(
        "Alerta de Notificación",
        "Then la notificación debe ocultarse\n",
    )
    assert clf.qc_relevance == "QC_FUNCTIONAL"
    mapped = translate_then_to_observable("la notificación debe ocultarse")
    assert mapped


def test_notificacion_se_oculta_is_qc_functional() -> None:
    clf = classify_scenario(
        "Alerta de Notificación",
        "Then la notificación se oculta\n",
    )
    assert clf.qc_relevance == "QC_FUNCTIONAL"


def test_rules_for_timeouts_do_not_create_independent_tc() -> None:
    description = """Feature: Calificación
  Rule: El tiempo máximo para cerrar la pantalla es de 60 segundos (max_display_time).
  Rule: display_time 30 segundos si el usuario no interactúa.
  Rule: post_vote_display_time 10 segundos tras una calificación.

    [Llave]
      vod_rating_settings
      | enable | true |
      | display_time | 30 |
      | post_vote_display_time | 10 |
      | max_display_time | 60 |
"""
    units = build_coverage_inventory(_story("STORY-RULE", description), "rn.pdf")
    assert units == []
    cases = candidates_from_jira_artifacts(
        _story("STORY-RULE", description), "rn.pdf", [], lambda *_args: None
    )
    assert cases == []


WEBCL_4142 = """Feature: Scroll del header
  Scenario: Transicion al hacer scroll hacia abajo
    When el usuario hace scroll hacia abajo y supera el umbral
    Then el gradient transiciona progresivamente de estado inicial a estado solido con blur
  Scenario: Retorno al hacer scroll hacia arriba
    When el usuario hace scroll hacia arriba por encima del umbral
    Then el gradient regresa a su estado inicial
"""


def test_webcl4142_scroll_stays_one_unit() -> None:
    artifacts = _story("WEBCL-4144", WEBCL_4142, epic="WEBCL-4142")
    units = build_coverage_inventory(artifacts, "rn.pdf")
    assert len(units) == 1
    cases = candidates_from_jira_artifacts(artifacts, "rn.pdf", [], lambda *_args: None)
    assert len(cases) == 1
    assert "scroll" in f"{units[0].scenario} {units[0].extra_test_data or ''}".lower()


STVCL_333_334 = """Feature: Funcionalidad del Módulo de Calificación
  Rule: Si rollingcreditstime tiene un valor igual a 0 continuar con FinPlayer.
  Rule: display_time 30, post_vote_display_time 10, max_display_time 60.

  Scenario: Creación de Pantalla de Calificacíon Post Reproducción con formato visual tipo PIP
    Given el usuario se encuentra en la pantalla de Post Reproducción con formato visual tipo PIP
    When se muestra la pantalla de calificacion "Post Reproducción con formato visual tipo PIP" con los elementos:
      | Elementos | Descripción |
      | Reproductor con formato visual tipo PIP | Vista reducida |
      | Contador del tiempo | Cuenta regresiva |
      | Botón Me gusta | Pulgar arriba |
      | Botón Cerrar | Icono X |
    Then la pantalla debe cumplir con las especificaciones solicitadas en los insumos de diseño.

  Scenario Outline: Calificación de Contenido
    Given el usuario se encuentra en la pantalla de calificación Post Reproducción
    And se muestra la botonera de Calificación
    When el usuario selecciona un botón para calificar
    Then el contenido fue calificado por el usuario correctamente
    And se muestra la botonera de Calificación
    Example:
      | <Calificación> | Descripción |
      | -1 | No me gusta |
      | 1 | Me gusta |
      | 2 | Me encanta |

  Scenario: Alerta de Notificación de calificación previa
    Given el usuario realiza una nueva calificación del contenido
    When la notificación de la calificación anterior aún se muestra en pantalla
    Then la notificación se debe ocultar
"""


def test_stvcl333_recovers_layout_rating_variants_and_notification() -> None:
    artifacts = _story("STVCL-334", STVCL_333_334, epic="STVCL-333")
    units = build_coverage_inventory(artifacts, "rn.pdf")
    scenarios = {unit.scenario for unit in units}
    assert any("Creación" in title for title in scenarios)
    assert any("Calificación de Contenido" in title for title in scenarios)
    assert any("Notificación" in title for title in scenarios)
    rating = next(unit for unit in units if "Calificación de Contenido" in unit.scenario)
    extra = (rating.extra_test_data or "").lower()
    assert extra.count("-1") >= 1 and "no me gusta" in extra and "me encanta" in extra
    assert not any("30" in unit.scenario and "display" in unit.scenario.lower() for unit in units)
    cases = candidates_from_jira_artifacts(artifacts, "rn.pdf", [], lambda *_args: None)
    assert len(cases) == len(units)
    assert 3 <= len(units) <= 4
