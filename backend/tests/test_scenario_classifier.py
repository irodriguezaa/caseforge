"""Scenario classification: observable Then vs implementation-only."""

from app.services.gherkin_coverage import (
    build_coverage_inventory,
    candidates_from_jira_artifacts,
    parse_gherkin_blocks,
)
from app.services.scenario_classifier import classify_scenario

STORY_ACCOUNT = """Feature: Pantalla de Ticket
  Scenario: Visualización del Ticket actualizado
      When el usuario visualiza la pantalla de Ticket
      Then se deben mostrar los elementos visuales actualizados conforme a los insumos de diseño
      And el diseño debe ser consistente con los estilos de los insumos

    Scenario: Lectura de la cuenta desde el contrato de confirmación
      Given el flujo de compra ejecutó exitosamente la API `v2/buyconfirm`
      When la aplicación construye la pantalla de Ticket
      Then el sistema debe leer `paymentMethodData.account`
      And debe interpolar el valor en la leyenda PayPal
      And no debe requerirse cambio en el contrato existente

    Scenario: Manejo de cuenta no disponible
      Given que `paymentMethodData.account` es null
      When se muestra la leyenda PayPal
      Then la pantalla no debe presentar errores de renderizado
      And debe mantenerse el layout aprobado

      Scenario: No se logra obtener una llave
      Given una llave que construye la pantalla no se encuentra en el response de la API "/apa/metadata"
      When la aplicación intenta construir la leyenda
      Then el espacio donde debería mostrarse la leyenda debe mostrar la llave
      And la posición de los elementos de la pantalla debe mantenerse fija
      And el tamaño de los elementos de la pantalla debe mantenerse fijo
      And no debe mostrarse un texto de error visible para el usuario

    Scenario: La llave se encuentra vacía
      Given una llave que construye la pantalla está vacía en el response de la API "/apa/metadata"
      When la aplicación intenta construir la leyenda
      Then el espacio donde debería mostrarse la leyenda debe quedar vacío
      And la posición de los elementos de la pantalla debe mantenerse fija
      And el tamaño de los elementos de la pantalla debe mantenerse fijo
      And no debe mostrarse un texto de error visible para el usuario

    Scenario: Visualización de Ticket con método de pago asociado
      Given el usuario adquirió exitosamente un contenido disponible
      When el usuario visualiza la pantalla de Ticket
      Then el sistema muestra la pantalla de Ticket con el método de pago asociado PayPal
      And se mantiene la estructura actual de la pantalla de Ticket
"""

STORY_TEXT = """Feature: Texto dinámico en Ticket
  Scenario: Mostrar texto informativo
    When el usuario transacciona con PayPal
    Then se debe mostrar el texto informativo correspondiente a PayPal
    And el texto debe incluir la cuenta PayPal asociada en formato usuario@dominio.com

  Scenario: Manejo de texto con longitud excedida
    When el texto informativo supera el límite permitido
    Then debe aplicarse el comportamiento actual
    And debe mostrarse "..." al final del texto

  Scenario: Visualización del texto PayPal en los flujos soportados
    When el usuario realiza una renta, compra o suscripción con PayPal asociado
    Then debe visualizarse el texto dinámico del método de pago PayPal
"""


def _roles(description: str) -> dict[str, str]:
    return {
        block["title"]: classify_scenario(block["title"], block["body"]).role
        for block in parse_gherkin_blocks(description)
    }


def test_missing_account_is_functional_when_screen_holds() -> None:
    clf = classify_scenario(
        "Manejo de cuenta no disponible",
        "Given que el dato de cuenta es null\n"
        "When se muestra la leyenda en pantalla\n"
        "Then la pantalla no debe presentar errores de renderizado\n"
        "And debe mantenerse el layout aprobado\n",
    )
    assert clf.role in {"A", "G"}
    assert clf.observable_then


def test_missing_key_is_functional_when_user_sees_key_without_error() -> None:
    clf = classify_scenario(
        "No se logra obtener una llave",
        "Given una llave no se encuentra en el response\n"
        "When la aplicación intenta construir la leyenda\n"
        "Then el espacio donde debería mostrarse la leyenda debe mostrar la llave\n"
        "And no debe mostrarse un texto de error visible para el usuario\n",
    )
    assert clf.role in {"A", "G"}
    assert any("llave" in item.lower() or "error" in item.lower() for item in clf.observable_then)


def test_empty_key_is_functional_when_slot_stays_empty() -> None:
    clf = classify_scenario(
        "La llave se encuentra vacía",
        "Given una llave está vacía en el response\n"
        "When la aplicación intenta construir la leyenda\n"
        "Then el espacio donde debería mostrarse la leyenda debe quedar vacío\n"
        "And no debe mostrarse un texto de error visible para el usuario\n",
    )
    assert clf.role in {"A", "G"}


def test_truncated_text_is_functional_when_ellipsis_is_visible() -> None:
    clf = classify_scenario(
        "Manejo de texto con longitud excedida",
        "When el texto informativo supera el límite permitido\n"
        "Then debe aplicarse el comportamiento actual\n"
        'And debe mostrarse "..." al final del texto\n',
    )
    assert clf.role in {"A", "G"}
    assert any("..." in item or "trunc" in item.lower() for item in clf.observable_then)


def test_supported_flows_are_functional_from_visible_text() -> None:
    clf = classify_scenario(
        "Visualización del texto en los flujos soportados",
        "When el usuario realiza una renta, compra o suscripción\n"
        "Then debe visualizarse el texto dinámico del método de pago\n",
    )
    assert clf.role in {"A", "G"}


def test_read_and_map_field_without_user_then_stays_implementation() -> None:
    clf = classify_scenario(
        "Lectura de la cuenta desde el contrato de confirmación",
        "Given el flujo ejecutó la API `v2/buyconfirm`\n"
        "When la aplicación construye la pantalla\n"
        "Then el sistema debe leer `paymentMethodData.account`\n"
        "And debe interpolar el valor en la leyenda PayPal\n"
        "And no debe requerirse cambio en el contrato existente\n",
    )
    assert clf.role == "C"


def test_metrics_only_stays_d() -> None:
    clf = classify_scenario(
        "Se registra evento payment_method_selected",
        "When el backend envía la métrica\nThen el esquema de métricas cumple el pipeline\n",
    )
    assert clf.role == "D"


def test_config_without_observable_stays_b() -> None:
    clf = classify_scenario(
        "Obtención de configuración remota",
        "Given la llave de configuración regional\n"
        "When el backend devuelve module_version=2\n"
        "Then se obtiene la configuración por región\n",
    )
    assert clf.role == "B"


def test_technical_when_does_not_block_observable_then() -> None:
    clf = classify_scenario(
        "Resiliencia de leyenda",
        "When la aplicación obtiene el payload y mapea el campo\n"
        "Then el usuario visualiza la leyenda y no se muestra error visible para el usuario\n",
    )
    assert clf.role in {"A", "G"}


def test_adrpr_style_story_roles() -> None:
    roles = _roles(STORY_ACCOUNT)
    assert roles["Visualización del Ticket actualizado"] in {"A", "G"}
    assert roles["Lectura de la cuenta desde el contrato de confirmación"] == "C"
    assert roles["Manejo de cuenta no disponible"] in {"A", "G"}
    assert roles["No se logra obtener una llave"] in {"A", "G"}
    assert roles["La llave se encuentra vacía"] in {"A", "G"}
    assert roles["Visualización de Ticket con método de pago asociado"] in {"A", "G"}
    text_roles = _roles(STORY_TEXT)
    assert text_roles["Mostrar texto informativo"] in {"A", "G"}
    assert text_roles["Manejo de texto con longitud excedida"] in {"A", "G"}
    assert text_roles["Visualización del texto PayPal en los flujos soportados"] in {"A", "G"}


def _artifacts() -> list[dict]:
    return [
        {
            "key": "EPIC-1",
            "issuetype": "Epic",
            "summary": "Feature EPIC-1",
            "description": "",
            "acceptance_criteria": "",
            "children": [
                {
                    "key": "STORY-A",
                    "issuetype": "Story",
                    "summary": "Feature STORY-A",
                    "description": STORY_ACCOUNT,
                    "acceptance_criteria": "",
                },
                {
                    "key": "STORY-B",
                    "issuetype": "Story",
                    "summary": "Feature STORY-B",
                    "description": STORY_TEXT,
                    "acceptance_criteria": "",
                },
            ],
        }
    ]


def test_inventory_covers_observable_gaps_without_tripling_flows() -> None:
    units = build_coverage_inventory(_artifacts(), "rn.pdf")
    scenarios = {unit.scenario for unit in units}
    assert "Manejo de cuenta no disponible" in scenarios
    assert "No se logra obtener una llave" in scenarios
    assert "La llave se encuentra vacía" in scenarios
    assert "Manejo de texto con longitud excedida" in scenarios
    assert "Visualización del texto PayPal en los flujos soportados" in scenarios
    assert "Lectura de la cuenta desde el contrato de confirmación" not in scenarios
    assert len(units) == 8
    for unit in units:
        assert unit.role in {"A", "G"}
        assert "EPIC-1" in unit.traceability
        assert unit.jira_key
        assert unit.scenario
        assert unit.observable_then
    flow_units = [unit for unit in units if "flujos soportados" in unit.scenario]
    assert len(flow_units) == 1


def test_materialized_steps_hide_implementation_tokens() -> None:
    cases = candidates_from_jira_artifacts(_artifacts(), "rn.pdf", [], lambda *_args: None)
    names = [item.name for item in cases]
    flow_hits = [name for name in names if "renta" in name.lower() or "suscrip" in name.lower()]
    assert len(flow_hits) <= 1
    blob = " ".join(
        f"{item.name} {step.action} {step.expected_result}"
        for item in cases
        for step in item.steps
    )
    assert "paymentMethodData" not in blob
    assert "la aplicación construye" not in blob.lower()
    missing_key = next(
        item
        for item in cases
        if "No se logra obtener una llave" in (item.evidence or "")
    )
    key_expected = " ".join(step.expected_result for step in missing_key.steps)
    assert "llave" in key_expected.lower()
    assert "error" in key_expected.lower()
    joined_evidence = " | ".join(item.evidence or "" for item in cases)
    assert "Manejo de cuenta no disponible" in joined_evidence
    assert "No se logra obtener una llave" in joined_evidence
    assert "La llave se encuentra vacía" in joined_evidence
    assert "longitud excedida" in joined_evidence
    assert "flujos soportados" in joined_evidence
    covers = [cid for item in cases for cid in item.covers]
    assert covers
    assert all(item.justification for item in cases)
