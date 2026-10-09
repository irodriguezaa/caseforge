"""Phase 1 inventory: atomize Then, keep user When, AC-without-Gherkin. No merge changes."""

from app.schemas.case_generation import GenerationStats
from app.services.gherkin_coverage import build_coverage_inventory, materialize_coverage_units


def _epic(key: str, story_key: str, description: str = "", ac: str = "") -> list[dict]:
    return [
        {
            "key": key,
            "issuetype": "Technical Epic",
            "summary": key,
            "description": "",
            "acceptance_criteria": "",
            "children": [
                {
                    "key": story_key,
                    "issuetype": "Technical Story",
                    "summary": story_key,
                    "description": description,
                    "acceptance_criteria": ac,
                }
            ],
        }
    ]


def _blob(units) -> str:
    parts = []
    for unit in units:
        parts.append(unit.scenario or "")
        parts.append(unit.behavior or "")
        parts.append(" ".join(unit.observable_then or []))
        parts.append(unit.body or "")
        parts.append(unit.user_action or "")
    return " ".join(parts).lower()


def test_adtcl_2323_ac_without_gherkin_creates_functional_units() -> None:
    ac = (
        "El panel de audios y subtítulos refleja la configuración cargada para el usuario.\n"
        "Si no existe configuración, se aplica el comportamiento por defecto del dispositivo "
        "y el usuario lo visualiza en el Player VOD.\n"
        "La continuidad de la experiencia se mantiene: el resto de funcionalidades no se ve afectado.\n"
        "Los textos configurables se reflejan en el Player VOD para el usuario.\n"
        "La aplicación invoca GET /player/config y el status code es 200.\n"
        "module_version se actualiza en apa/metadata.\n"
    )
    stats = GenerationStats()
    before = build_coverage_inventory(
        _epic("ADTCL-2323", "ADTCL-2324", description="Sin escenarios Gherkin.", ac=""),
        "rn.pdf",
        stats=GenerationStats(),
    )
    after = build_coverage_inventory(
        _epic("ADTCL-2323", "ADTCL-2324", description="", ac=ac),
        "rn.pdf",
        stats=stats,
    )
    assert len(before) == 0
    assert len(after) >= 4
    text = _blob(after)
    assert "reflej" in text and "configuraci" in text
    assert "defecto" in text or "default" in text
    assert "continuidad" in text or "no se ve afect" in text
    assert "textos configurables" in text or "player vod" in text
    assert all(unit.source_origin in {"ac", "description"} for unit in after)
    assert any("HTTP/API" in row or "configuración pura" in row for row in stats.inventory_exclusions)


def test_adtcl_2323_live_epic_ac_complements_story_gherkin() -> None:
    """AC lives on the epic; Gherkin lives on the story. Both must feed inventory."""
    gherkin = '''
Feature: Registro de llaves de configuración en appKeys
  Background:
    Given que la aplicación no dispone actualmente de las llaves requeridas
  Scenario: Creación de llaves de configuración en appKeys
    When se registran las llaves necesarias en las appKeys del dispositivo
    Then dichas llaves deben estar disponibles para cada plataforma participante
  Scenario: Gestión dinámica de configuraciones
    Given que las llaves de configuración están registradas en las appKeys
    When un administrador modifica parámetros desde la herramienta de administración
    Then los cambios se aplican dinámicamente sin necesidad de modificar el código fuente
  Scenario: Reflejo correcto de configuraciones en dispositivos
    Given que existen configuraciones personalizadas registradas en appKeys
    When los dispositivos del proyecto cargan el proyecto
    Then las configuraciones deben reflejarse correctamente sin errores de carga ni problemas de formato
  Scenario: Validación de no regresión en funcionalidades
    When se habilita la configuración dinámica mediante las nuevas llaves
    Then otras funcionalidades y configuraciones no relacionadas no deben verse afectadas
'''
    ac = (
        "Las llaves de configuración necesarias se encuentran registradas en las appKeys "
        "de todos los dispositivos incluidos en el alcance del proyecto.\n"
        "Los textos y valores configurables pueden editarse desde la herramienta de "
        "administración sin requerir modificaciones en el código ni despliegues adicionales.\n"
        "Las configuraciones se reflejan correctamente en los dispositivos, manteniendo "
        "el formato y comportamiento definidos en el proyecto.\n"
        "Si alguna llave de configuración no existe o no es devuelta por el servicio, "
        "el sistema utiliza el valor por defecto definido en el código para mantener "
        "el comportamiento esperado del dispositivo.\n"
        "La incorporación de estas llaves no afecta otras funcionalidades o "
        "configuraciones existentes en la plataforma.\n"
    )
    artifacts = [
        {
            "key": "ADTCL-2323",
            "issuetype": "Technical Epic",
            "summary": "ADTCL-2323",
            "description": "",
            "acceptance_criteria": ac,
            "children": [
                {
                    "key": "ADTCL-2324",
                    "issuetype": "Technical Story",
                    "summary": "ADTCL-2324",
                    "description": gherkin,
                    "acceptance_criteria": "",
                }
            ],
        }
    ]
    units = build_coverage_inventory(artifacts, "rn.pdf")
    text = _blob(units)
    origins = {unit.source_origin for unit in units}
    assert "ac" in origins
    assert "reflej" in text
    assert "defecto" in text or "default" in text
    assert "no afecta" in text or "verse afectadas" in text or "continuidad" in text
    assert "textos" in text and "configurables" in text
    assert not any(
        "creación de llaves" in (unit.scenario or "").lower()
        and unit.source_origin == "gherkin"
        for unit in units
    )


def test_adtcl_2323_ac_complements_technical_gherkin() -> None:
    description = """
Scenario: Creación de llaves de configuración en appKeys
  When el backend publica las llaves
  Then se crean las llaves en apa/metadata
Scenario: Gestión dinámica de configuraciones
  When admin edita appKeys
  Then module_version se actualiza
"""
    ac = (
        "El panel de audios y subtítulos refleja la configuración cargada para el usuario.\n"
        "Si no existe configuración, se aplica el comportamiento por defecto del dispositivo "
        "y el usuario lo visualiza en el Player VOD.\n"
        "La continuidad de la experiencia se mantiene: el resto de funcionalidades no se ve afectado.\n"
        "Los textos configurables se reflejan en el Player VOD para el usuario.\n"
    )
    units = build_coverage_inventory(
        _epic("ADTCL-2323", "ADTCL-2324", description=description, ac=ac),
        "rn.pdf",
    )
    text = _blob(units)
    assert "reflej" in text and "configuraci" in text
    assert "defecto" in text or "default" in text
    assert "continuidad" in text or "no se ve afect" in text
    assert "textos configurables" in text or "player vod" in text
    assert any(unit.source_origin == "ac" for unit in units)
    assert len([unit for unit in units if unit.source_origin == "ac"]) >= 4


def test_http_only_without_consequence_is_excluded() -> None:
    stats = GenerationStats()
    units = build_coverage_inventory(
        _epic(
            "ADTCL-1",
            "ADTCL-2",
            description="Scenario: Invocar config\n  When el backend llama GET /player/config\n  Then el status code es 200\n",
        ),
        "rn.pdf",
        stats=stats,
    )
    assert units == []
    assert any("HTTP/API" in row or "observable" in row.lower() for row in stats.inventory_exclusions)


def test_api_with_observable_consequence_is_kept() -> None:
    units = build_coverage_inventory(
        _epic(
            "ADTCL-1",
            "ADTCL-2",
            description=(
                "Scenario: Error de media\n"
                "  When el usuario reproduce el contenido\n"
                "  Then se muestra el estado de no disponible en pantalla\n"
                "  And GET /player/getmedia responde 400\n"
            ),
        ),
        "rn.pdf",
    )
    assert units
    text = _blob(units)
    assert "no disponible" in text or "pantalla" in text


def test_config_with_observable_behavior_is_kept() -> None:
    units = build_coverage_inventory(
        _epic(
            "ADTCL-2323",
            "ADTCL-2324",
            ac="Los textos configurables se reflejan en el Player VOD para el usuario.\n",
        ),
        "rn.pdf",
    )
    assert units
    assert "player vod" in _blob(units) or "textos configurables" in _blob(units)


def test_technical_implementation_without_ux_is_excluded() -> None:
    stats = GenerationStats()
    units = build_coverage_inventory(
        _epic(
            "ADTCL-2323",
            "ADTCL-2324",
            description=(
                "Scenario: Creación de llaves de configuración en appKeys\n"
                "  When el backend publica las llaves\n"
                "  Then se crean las llaves en apa/metadata\n"
            ),
        ),
        "rn.pdf",
        stats=stats,
    )
    assert not any("appkeys" in (unit.scenario or "").lower() for unit in units)


def test_adtcl_2394_atomizes_independent_observables() -> None:
    description = """
Scenario: Reproducción del canal configurado por default en el primer acceso a TV en vivo
  Given es la primera vez que el usuario accede a TV en vivo
  When el usuario ingresa a TV en vivo
  Then se reproduce el canal configurado por default por la operación

Scenario: Reproducción del último canal visto por el perfil
  Given el perfil ya ha visto un canal
  When el usuario reingresa a TV en vivo
  Then se reproduce el último canal visto por ese perfil

Scenario: Navegación entre canales contratados usando CH+ o Derecha
  When el usuario presiona CH+
  Then el player cambia al siguiente canal contratado
  And no se sintonizan canales intermedios no contratados

Scenario: Ingreso de dígitos para cambio de canal
  When el usuario digita desde el RCU el primer dígito de un canal
  Then se oculta el panel de metadata de eventos presentes
  And se muestran en pantalla los dígitos ingresados en tiempo real
  And se visualizan dashes indicando los dígitos restantes
  And al transcurrir 3 segundos se cambia automáticamente de canal
  And al completar el máximo de dígitos se cambia automáticamente de canal

Scenario: Cancelar digitalización de canal
  When el usuario presiona Back
  Then se cancela la digitación de canal
  And se borran y ocultan los números digitados
  And el usuario permanece en la pantalla de origen
  And se restaura el panel de metadata

Scenario: Back sin digitación en curso
  Given no hay digitación en curso
  When el usuario presiona Back
  Then continúa la reproducción del canal actual
"""
    stats = GenerationStats()
    units = build_coverage_inventory(
        _epic("ADTCL-2394", "ADTCL-2396", description=description),
        "rn.pdf",
        stats=stats,
    )
    text = _blob(units)
    assert "primer" in text or "default" in text
    assert "último canal" in text or "ultimo canal" in text
    assert "metadata" in text
    assert "dígitos" in text or "digitos" in text
    assert "dashes" in text
    assert "3 segundos" in text or "timeout" in text
    assert "máximo" in text or "maximo" in text
    assert "back" in text
    assert "no contratad" in text
    assert any("presiona back" in (unit.user_action or "").lower() for unit in units)
    assert any("ch+" in (unit.user_action or "").lower() for unit in units)
    assert len(units) > 6


def test_adtcl_541_keeps_panel_pause_audio_back_timeout() -> None:
    description = """
Scenario: Seleccionar botón Audio y Subtitulos en la botonera
  When el usuario selecciona el botón Audio y Subtítulos
  Then se muestra el Panel de Audio y Subtítulos
  And se pausa la reproducción del contenido

Scenario: Panel de Audio y Subtítulos
  When el usuario abre el Panel de Audio y Subtítulos
  Then se identifica el audio actual del contenido
  And se identifica el subtítulo actual del contenido
  And se muestran los elementos del panel según diseño

Scenario: Nueva selección de Audio
  When el usuario selecciona una opción de Audio
  Then se aplica el cambio de audio
  And aparece el check en la opción seleccionada
  And el Panel permanece abierto

Scenario: Nueva selección de Subtitulos
  When el usuario selecciona una nueva opción de subtítulos
  Then se aplican los subtítulos
  And al seleccionar Desactivados se desactivan los subtítulos
  And el Panel permanece desplegado

Scenario: Cerrar Panel de Audio y Subtitulos si no hay interaccion
  When transcurren 5 segundos de inactividad
  Then se cierra automáticamente el Panel de Audio y Subtítulos
  And se reanuda la reproducción desde el punto pausado

Scenario: Comportamiento del RCU
  When el usuario presiona Back
  Then se cierra el Panel de Audio y Subtítulos

Scenario: Visualización del Panel con la nueva experiencia habilitada
  Given la nueva experiencia está habilitada
  When el usuario abre el Panel de Audio y Subtítulos
  Then se muestra el Panel con la nueva experiencia

Scenario: Visualización del Panel con la experiencia anterior
  Given la nueva experiencia está deshabilitada
  When el usuario abre el Panel de Audio y Subtítulos
  Then se muestra el Panel con la experiencia anterior

Scenario: Recuperación de la última preferencia de idioma
  When el usuario reproduce un contenido VOD
  Then se recupera la última preferencia de idioma
"""
    units = build_coverage_inventory(
        _epic("ADTCL-541", "ADTCL-544", description=description),
        "rn.pdf",
    )
    text = _blob(units)
    for token in (
        "panel",
        "pausa",
        "audio actual",
        "subtítulo actual",
        "check",
        "desactiv",
        "reanuda",
        "back",
        "nueva experiencia",
        "preferencia",
    ):
        assert token in text, token
    assert any("selecciona" in (unit.user_action or "").lower() for unit in units)


def test_adtcl_141_preserves_intent_in_source_when() -> None:
    description = """
Scenario: Solicitar PIN de seguridad (PIN correcto)
  When el usuario selecciona un evento de canal bloqueado
  Then se muestra pantalla para ingresar PIN de seguridad
  When el usuario ingresa PIN de seguridad
  Then el usuario visualiza el contenido

Scenario: Solicitar PIN de seguridad para grabar un evento
  Given se muestra pantalla de Opciones del Programa
  When el usuario da clic en el botón Grabar programa
  Then se muestra la pantalla Ingresar PIN de seguridad

Scenario: Solicitar PIN de seguridad para cancelar grabacion
  When el usuario selecciona Cancelar grabación
  Then se muestra pantalla para ingresar PIN de seguridad

Scenario: Solicitar PIN de seguridad para añadir un canal a favoritos
  When el usuario selecciona añadir a favoritos
  Then se muestra pantalla para ingresar PIN de seguridad

Scenario: Solicitar PIN de seguridad al desbloquear un canal
  When el usuario selecciona Desbloquear Canal
  Then se muestra pantalla para ingresar PIN de seguridad
"""
    units = build_coverage_inventory(
        _epic("ADTCL-141", "ADTCL-142", description=description),
        "rn.pdf",
    )
    actions = " ".join((unit.user_action or "") + " " + (unit.body or "") for unit in units).lower()
    assert "grabar" in actions
    assert "cancelar" in actions
    assert "favoritos" in actions
    assert "desbloquear" in actions
    generic = "el usuario ingresa al flujo correspondiente."
    assert not any((unit.user_action or "").strip().lower() == generic for unit in units)


def _no_dup(_name: str, _jira: str | None, _existing: list[dict[str, str]]) -> None:
    return None


def test_qc_022_023_033_preserve_original_user_when() -> None:
    """Inventory must keep Grabar / Back / PIN When; never replace with the generic fallback."""
    description = """
Scenario: QC-022 Solicitar PIN de seguridad para grabar un evento
  Given se muestra pantalla de Opciones del Programa
  When el usuario selecciona Grabar
  Then se muestra la pantalla Ingresar PIN de seguridad

Scenario: QC-023 Cancelar digitalización de canal
  When el usuario presiona Back
  Then se cancela la digitación de canal
  And se restaura el panel de metadata

Scenario: QC-033 Solicitar PIN de seguridad (PIN correcto)
  When el usuario ingresa PIN de seguridad
  Then el usuario visualiza el contenido
"""
    units = build_coverage_inventory(
        _epic("ADTCL-141", "ADTCL-142", description=description),
        "rn.pdf",
    )
    generic = "el usuario ingresa al flujo correspondiente."
    actions = " ".join((unit.user_action or "").lower() for unit in units)
    assert "selecciona grabar" in actions
    assert "presiona back" in actions
    assert "ingresa pin" in actions
    assert not any((unit.user_action or "").strip().lower() == generic for unit in units)

    candidates = materialize_coverage_units(units, [], _no_dup)
    step_actions = " ".join(
        step.action.lower() for cand in candidates for step in cand.steps
    )
    assert "selecciona grabar" in step_actions
    assert "presiona back" in step_actions
    assert "ingresa pin" in step_actions
    assert not any(
        (step.action or "").strip().lower() == generic
        for cand in candidates
        for step in cand.steps
    )


def test_http_example_does_not_create_one_unit_per_status() -> None:
    description = """
Scenario Outline: Validar respuesta de PIN
  When el usuario ingresa PIN de seguridad
  Then se muestra el resultado de PIN en pantalla
  Examples:
    | code |
    | 200  |
    | 400  |
"""
    units = build_coverage_inventory(
        _epic("ADTCL-141", "ADTCL-142", description=description),
        "rn.pdf",
    )
    assert len(units) == 1


def test_legend_key_template_is_dropped_on_banner_feature_not_ticket() -> None:
    """Stock leyenda-key Gherkin is QC on Ticket/leyenda Features, not on a banner Feature."""
    banner_gherkin = """
Feature: Implementar banner con políticas de cookies
  Scenario: Mostrar automáticamente el banner informativo de cookies
    When la Landing Page termina de cargar
    Then se debe mostrar el banner informativo de cookies
  Scenario: Redirección a la política de cookies al seleccionar el enlace
    Given el banner informativo de cookies está visible
    When el usuario hace clic en el enlace configurado en los insumos de diseño
    Then el navegador debe redirigir al usuario a la URL de la política de cookies
  Scenario: No se logra obtener una llave
    Given una llave no se encuentra en apa/metadata
    When la aplicación intenta construir la leyenda
    Then el espacio donde debería mostrarse la leyenda debe mostrar la llave
  Scenario: La llave se encuentra vacía
    Given una llave está vacía en apa/metadata
    When la aplicación intenta construir la leyenda
    Then el espacio donde debería mostrarse la leyenda debe quedar vacía
"""
    ticket_gherkin = """
Feature: Pantalla de Ticket
  Scenario: No se logra obtener una llave
    Given una llave no se encuentra en apa/metadata
    When la aplicación intenta construir la leyenda
    Then el espacio donde debería mostrarse la leyenda debe mostrar la llave
    And no debe mostrarse un texto de error visible para el usuario
"""
    banner_units = build_coverage_inventory(
        [
            {
                "key": "EPC-BANNER",
                "issuetype": "Technical Epic",
                "summary": "Banner de cookies",
                "description": "",
                "acceptance_criteria": (
                    "El banner se muestra automáticamente cuando no existe consentimiento previo válido.\n"
                    "La redirección a la página oficial de la política completa de cookies funciona correctamente.\n"
                ),
                "children": [
                    {
                        "key": "STORY-BANNER",
                        "issuetype": "Technical Story",
                        "summary": "Feature: Implementar banner con políticas de cookies",
                        "description": banner_gherkin,
                        "acceptance_criteria": "",
                    }
                ],
            }
        ],
        "rn.pdf",
    )
    names = " ".join((unit.scenario or "").lower() for unit in banner_units)
    assert "no se logra obtener una llave" not in names
    assert "llave se encuentra vac" not in names
    assert any("banner" in (unit.scenario or "").lower() for unit in banner_units)
    assert any("redir" in (unit.scenario or "").lower() for unit in banner_units)
    assert any(
        "landing" in (unit.user_action or "").lower()
        for unit in banner_units
        if unit.user_action
    )
    assert any(
        "clic" in (unit.user_action or "").lower() or "enlace" in (unit.user_action or "").lower()
        for unit in banner_units
        if unit.user_action
    )

    ticket_units = build_coverage_inventory(
        [
            {
                "key": "EPC-TICKET",
                "issuetype": "Technical Epic",
                "summary": "Pantalla de Ticket",
                "description": "",
                "acceptance_criteria": "",
                "children": [
                    {
                        "key": "STORY-TICKET",
                        "issuetype": "Technical Story",
                        "summary": "Feature: Pantalla de Ticket",
                        "description": ticket_gherkin,
                        "acceptance_criteria": "",
                    }
                ],
            }
        ],
        "rn.pdf",
    )
    ticket_names = {(unit.scenario or "") for unit in ticket_units}
    assert "No se logra obtener una llave" in ticket_names


def test_page_load_when_is_preserved_as_entry_action() -> None:
    description = """
Scenario: Mostrar banner al cargar
  When la Landing Page termina de cargar
  Then se debe mostrar el banner informativo de cookies
"""
    units = build_coverage_inventory(
        _epic("EPC-1", "STORY-1", description=description),
        "rn.pdf",
    )
    assert units
    assert any(
        "landing" in (unit.user_action or "").lower()
        or "ingresa" in (unit.user_action or "").lower()
        for unit in units
    )
    assert all(
        (unit.user_action or "").lower() != "el usuario ingresa al flujo correspondiente."
        for unit in units
    )


def test_redirect_then_is_coverable_user_navigation() -> None:
    from app.services.scenario_classifier import classify_scenario

    clf = classify_scenario(
        "Redirección a la política de cookies al seleccionar el enlace",
        "Given el banner informativo de cookies está visible\n"
        "When el usuario hace clic en el enlace configurado en los insumos de diseño\n"
        "Then el navegador debe redirigir al usuario a la URL de la política de cookies\n",
    )
    assert clf.role in {"A", "G"}
    assert clf.qc_relevance in {"QC_FUNCTIONAL", "QC_REGRESSION", "QC_VARIANT"}
    assert clf.observable_then or clf.qc_observables


def test_webcl_1900_cookie_ac_not_stv_legend_keys() -> None:
    """Cookie banner AC is QC; STB-style 'llave' Gherkin without leyenda is not."""
    gherkin = """
Feature: Banner informativo de cookies
  Scenario: Mostrar banner informativo de cookies
    When el usuario ingresa al sitio sin consentimiento previo
    Then el banner de cookies se muestra automáticamente
  Scenario: No mostrar banner informativo de cookies
    Given existe consentimiento previo válido
    When el usuario ingresa al sitio
    Then el banner de cookies no se muestra
  Scenario: No se logra obtener una llave
    Given no se obtiene una llave
    When la aplicación intenta leer la llave
    Then no se logra obtener una llave
  Scenario: La llave se encuentra vacía
    Given la llave se encuentra vacía
    When la aplicación intenta leer la llave
    Then la llave se encuentra vacía
"""
    ac = (
        "El banner se muestra automáticamente cuando no existe consentimiento previo válido.\n"
        "El consentimiento se registra correctamente al seleccionar ACEPTAR.\n"
        "Una vez aceptadas las cookies, el banner no debe volver a mostrarse mientras "
        "la política de cookies permanezca vigente.\n"
        "El consentimiento debe solicitarse nuevamente únicamente cuando exista una "
        "nueva versión vigente de la política de cookies.\n"
        "La redirección a la página oficial de la política completa de cookies de "
        "Claro funciona correctamente.\n"
    )
    artifacts = [
        {
            "key": "WEBCL-1900",
            "issuetype": "Technical Epic",
            "summary": "Banner cookies",
            "description": "",
            "acceptance_criteria": ac,
            "children": [
                {
                    "key": "WEBCL-1901",
                    "issuetype": "Technical Story",
                    "summary": "Banner cookies",
                    "description": gherkin,
                    "acceptance_criteria": "",
                },
                {
                    "key": "WEBCL-1902",
                    "issuetype": "Technical Story",
                    "summary": "Setup de métricas cookies",
                    "description": (
                        "Scenario: Implementación inicial del setup de métricas\n"
                        "  When el backend envía la métrica\n"
                        "  Then el esquema de métricas cumple el pipeline\n"
                    ),
                    "acceptance_criteria": "",
                },
            ],
        }
    ]
    stats = GenerationStats()
    units = build_coverage_inventory(artifacts, "rn.pdf", stats=stats)
    names = " ".join((unit.scenario or "").lower() for unit in units)
    text = _blob(units)
    assert "no se logra obtener una llave" not in names
    assert "llave se encuentra vac" not in names
    assert "métric" not in names
    assert "banner" in text
    assert "aceptar" in text or "consentimiento" in text
    assert "versi" in text
    assert "redirec" in text or "pol" in text


