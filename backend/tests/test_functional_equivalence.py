"""Phase 2: merge only on functional_equivalence_key, never on Expected/PIN/key alone."""

from app.schemas.case_generation import CandidateStep, CoverageUnit, GeneratedCaseCandidate
from app.services.executability import STABLE_GENERIC_STEP
from app.services.functional_equivalence import (
    build_functional_equivalence_key,
    functionally_equivalent,
)
from app.services.gherkin_coverage import build_coverage_inventory, candidates_from_jira_artifacts
from app.services.qc_candidate_rules import apply_qc_rules
from tests.test_inventory_atomize import _epic


def _unit(
    *,
    cid: str,
    epic: str,
    scenario: str,
    action: str | None,
    observable: str,
    condition: str | None = None,
    story: str | None = None,
) -> CoverageUnit:
    return CoverageUnit(
        coverage_id=cid,
        role="G",
        behavior=scenario,
        scenario=scenario,
        evidence=f"{story or epic}: {scenario}",
        jira_key=story or epic,
        rn_key=epic,
        feature_story=story or epic,
        artifact_key=epic,
        story_key=story or epic,
        user_action=action,
        observable_then=[observable],
        special_condition=condition,
        test_intent=scenario,
        body=f"When {action or ''}\nThen {observable}",
    )


def _cand(
    *,
    name: str,
    epic: str,
    action: str,
    expected: str,
    covers: list[str],
    precondition: str | None = None,
    story: str | None = None,
) -> GeneratedCaseCandidate:
    return GeneratedCaseCandidate(
        name=name,
        description=name,
        precondition=precondition,
        steps=[CandidateStep(step_number=1, action=action, expected_result=expected)],
        related_functionality=epic,
        related_jira=story or epic,
        evidence=name,
        justification="fixture",
        covers=covers,
    )


def test_build_functional_equivalence_key_is_normalized_not_raw_concat() -> None:
    left = _unit(
        cid="COV-001",
        epic="ADTCL-100",
        scenario="Calificar contenido (Me gusta)",
        action="El usuario selecciona Me gusta",
        observable="Se aplica la calificación en pantalla",
    )
    right = _unit(
        cid="COV-002",
        epic="ADTCL-100",
        scenario="Calificar contenido (ME  GUSTA)",
        action="el usuario selecciona me gusta",
        observable="se aplica la calificacion en pantalla",
    )
    key = build_functional_equivalence_key(left)
    assert key.epic == "ADTCL-100"
    assert key.objective == "calificar"
    assert key.value() == build_functional_equivalence_key(right).value()
    assert "me gusta" not in key.value()


def test_must_merge_rating_serie_resume_http() -> None:
    rating = [
        _cand(
            name="Calificar No me gusta",
            epic="WEBCL-1",
            action="El usuario selecciona No me gusta",
            expected="Se aplica la calificación",
            covers=["COV-R1"],
        ),
        _cand(
            name="Calificar Me gusta",
            epic="WEBCL-1",
            action="El usuario selecciona Me gusta",
            expected="Se aplica la calificación",
            covers=["COV-R2"],
        ),
        _cand(
            name="Calificar Me encanta",
            epic="WEBCL-1",
            action="El usuario selecciona Me encanta",
            expected="Se aplica la calificación",
            covers=["COV-R3"],
        ),
    ]
    merged_rating = apply_qc_rules(rating)
    assert len(merged_rating) == 1
    assert set(merged_rating[0].covers) == {"COV-R1", "COV-R2", "COV-R3"}

    serie = _cand(
        name="Reanudar serie",
        epic="WEBCL-2",
        action="El usuario selecciona Reanudar",
        expected="Continúa la reproducción del contenido",
        covers=["COV-S1"],
    )
    episodio = _cand(
        name="Reanudar episodio",
        epic="WEBCL-2",
        action="El usuario selecciona Reanudar",
        expected="Continúa la reproducción del episodio",
        covers=["COV-S2"],
    )
    assert functionally_equivalent(serie, episodio)
    assert len(apply_qc_rules([serie, episodio])) == 1

    inicio = _cand(
        name="Reproducir desde el inicio",
        epic="WEBCL-3",
        action="El usuario selecciona Desde el inicio",
        expected="El contenido se reproduce desde el inicio",
        covers=["COV-P1"],
    )
    ahora = _cand(
        name="Reproducir desde ahora",
        epic="WEBCL-3",
        action="El usuario selecciona Desde ahora",
        expected="El contenido se reproduce desde ahora",
        covers=["COV-P2"],
    )
    assert len(apply_qc_rules([inicio, ahora])) == 1

    http_ok = _cand(
        name="Validar PIN (HTTP 200)",
        epic="ADTCL-141",
        action="El usuario ingresa PIN de seguridad",
        expected="El usuario visualiza el contenido status 200",
        covers=["COV-H1"],
    )
    http_fail = _cand(
        name="Validar PIN (HTTP 400)",
        epic="ADTCL-141",
        action="El usuario ingresa PIN de seguridad",
        expected="El usuario visualiza el contenido",
        covers=["COV-H2"],
    )
    assert len(apply_qc_rules([http_ok, http_fail])) == 1


def test_must_not_merge_distinct_intents_or_epcs() -> None:
    reproducir = _cand(
        name="Reproducir evento bloqueado",
        epic="ADTCL-141",
        action="El usuario selecciona un evento de canal bloqueado",
        expected="Se muestra pantalla para ingresar PIN de seguridad",
        covers=["COV-1"],
        story="ADTCL-142",
    )
    grabar = _cand(
        name="Grabar evento",
        epic="ADTCL-141",
        action="El usuario selecciona Grabar",
        expected="Se muestra pantalla para ingresar PIN de seguridad",
        covers=["COV-2"],
        story="ADTCL-142",
    )
    cancelar = _cand(
        name="Cancelar grabación",
        epic="ADTCL-141",
        action="El usuario selecciona Cancelar grabación",
        expected="Se muestra pantalla para ingresar PIN de seguridad",
        covers=["COV-3"],
        story="ADTCL-142",
    )
    favorito = _cand(
        name="Añadir a favoritos",
        epic="ADTCL-141",
        action="El usuario selecciona añadir a favoritos",
        expected="Se muestra pantalla para ingresar PIN de seguridad",
        covers=["COV-4"],
        story="ADTCL-142",
    )
    desbloquear = _cand(
        name="Desbloquear canal",
        epic="ADTCL-141",
        action="El usuario selecciona Desbloquear Canal",
        expected="Se muestra pantalla para ingresar PIN de seguridad",
        covers=["COV-5"],
        story="ADTCL-142",
    )
    pin_group = apply_qc_rules([reproducir, grabar, cancelar, favorito, desbloquear])
    assert len(pin_group) == 5


def test_empty_action_does_not_merge_distinct_pin_intents() -> None:
    expected = "Se muestra pantalla para ingresar PIN de seguridad"

    def pin(title: str, covers: list[str]) -> GeneratedCaseCandidate:
        row = _cand(
            name=title,
            epic="ADTCL-141",
            action=STABLE_GENERIC_STEP,
            expected=expected,
            covers=covers,
            story="ADTCL-157",
        )
        row.description = title
        row.evidence = f"ADTCL-157: {title}"
        return row

    reproducir = pin("Pantalla de PIN de seguridad al reproducir una grabación", ["COV-R"])
    grabar = pin("Pantalla de PIN de seguridad al grabar un evento", ["COV-G"])
    cancelar = pin("Pantalla de PIN de seguridad al cancelar grabación", ["COV-C"])
    favoritos = pin("Pantalla de PIN de seguridad al agregar a favoritos", ["COV-F"])
    desbloquear = pin("Pantalla de PIN de seguridad al desbloquear un canal", ["COV-D"])
    assert not functionally_equivalent(reproducir, grabar)
    assert not functionally_equivalent(grabar, cancelar)
    assert not functionally_equivalent(favoritos, desbloquear)
    merged = apply_qc_rules([reproducir, grabar, cancelar, favoritos, desbloquear])
    assert len(merged) == 5

    rewritten = "se muestra pantalla para ingresar PIN de seguridad"
    empty_units = [
        _unit(
            cid="COV-R",
            epic="ADTCL-141",
            scenario="Solicitar PIN de seguridad al reproducir una grabación",
            action=None,
            observable=expected,
            story="ADTCL-157",
        ),
        _unit(
            cid="COV-G",
            epic="ADTCL-141",
            scenario="Solicitar PIN de seguridad para grabar un evento",
            action=None,
            observable=expected,
            story="ADTCL-157",
        ),
        _unit(
            cid="COV-C",
            epic="ADTCL-141",
            scenario="Solicitar PIN de seguridad para cancelar grabación",
            action=None,
            observable=expected,
            story="ADTCL-157",
        ),
        _unit(
            cid="COV-F",
            epic="ADTCL-141",
            scenario="Solicitar PIN de seguridad para añadir a favoritos",
            action=None,
            observable=expected,
            story="ADTCL-157",
        ),
        _unit(
            cid="COV-D",
            epic="ADTCL-141",
            scenario="Solicitar PIN de seguridad al desbloquear un canal",
            action=None,
            observable=expected,
            story="ADTCL-157",
        ),
    ]
    for unit in empty_units:
        unit.behavior = rewritten
        unit.body = f"Given el usuario inicia el flujo\nThen {expected}"
    assert not functionally_equivalent(empty_units[0], empty_units[1])
    assert not functionally_equivalent(empty_units[1], empty_units[2])
    assert not functionally_equivalent(empty_units[3], empty_units[4])
    eliminar_grab = _unit(
        cid="COV-EG",
        epic="ADTCL-141",
        scenario="Pantalla de PIN de seguridad al eliminar una grabación de un evento de un canal bloqueado",
        action=None,
        observable=expected,
        story="ADTCL-157",
    )
    eliminar_grab.behavior = rewritten
    eliminar_grab.body = f"Given el canal está bloqueado\nThen {expected}"
    reproducir_grab = _unit(
        cid="COV-RG",
        epic="ADTCL-141",
        scenario="Pantalla de PIN de seguridad al reproducir una grabación de un evento de un canal bloqueado",
        action=None,
        observable=expected,
        story="ADTCL-157",
    )
    reproducir_grab.behavior = rewritten
    reproducir_grab.body = f"Given el canal está bloqueado\nThen {expected}"
    assert not functionally_equivalent(eliminar_grab, reproducir_grab)

    rewritten_cands = []
    for title, cover in (
        ("Solicitar PIN de seguridad al reproducir una grabación", ["COV-R"]),
        ("Solicitar PIN de seguridad para grabar un evento", ["COV-G"]),
        ("Solicitar PIN de seguridad para cancelar grabación", ["COV-C"]),
        ("Solicitar PIN de seguridad para añadir a favoritos", ["COV-F"]),
        ("Solicitar PIN de seguridad al desbloquear un canal", ["COV-D"]),
    ):
        row = _cand(
            name=rewritten,
            epic="ADTCL-141",
            action=STABLE_GENERIC_STEP,
            expected=expected,
            covers=cover,
            story="ADTCL-157",
        )
        row.description = "PIN parental compartido en la historia"
        row.evidence = f"ADTCL-157: {title}\nThen {expected}"
        rewritten_cands.append(row)
    assert len(apply_qc_rules(rewritten_cands)) == 5

    audio = _cand(
        name="Seleccionar audio",
        epic="ADTCL-541",
        action="El usuario selecciona una opción de audio",
        expected="Se aplica el cambio de audio",
        covers=["COV-A"],
    )
    sub = _cand(
        name="Seleccionar subtítulo",
        epic="ADTCL-541",
        action="El usuario selecciona una opción de subtítulos",
        expected="Se aplican los subtítulos",
        covers=["COV-B"],
    )
    abrir = _cand(
        name="Abrir panel",
        epic="ADTCL-541",
        action="El usuario selecciona el botón Audio y Subtítulos",
        expected="Se muestra el Panel de Audio y Subtítulos",
        covers=["COV-C"],
    )
    back = _cand(
        name="Back cierra el panel",
        epic="ADTCL-541",
        action="El usuario presiona Back",
        expected="Se cierra el Panel de Audio y Subtítulos",
        covers=["COV-D"],
    )
    panel = apply_qc_rules([audio, sub, abrir, back])
    assert len(panel) == 4

    key_541 = _cand(
        name="No se logra obtener una llave",
        epic="ADTCL-541",
        action="El usuario ingresa al flujo correspondiente.",
        expected="El espacio de la leyenda muestra la llave",
        covers=["COV-K1"],
    )
    key_308 = _cand(
        name="No se logra obtener una llave",
        epic="ADTCL-308",
        action="El usuario ingresa al flujo correspondiente.",
        expected="El espacio de la leyenda muestra la llave",
        covers=["COV-K2"],
    )
    assert len(apply_qc_rules([key_541, key_308])) == 2
    other_epc = _cand(
        name="Calificar Me gusta",
        epic="ADTCL-999",
        action="El usuario selecciona Me gusta",
        expected="Se aplica la calificación",
        covers=["COV-X"],
    )
    same_rating = _cand(
        name="Calificar Me encanta",
        epic="WEBCL-1",
        action="El usuario selecciona Me encanta",
        expected="Se aplica la calificación",
        covers=["COV-Y"],
    )
    assert len(apply_qc_rules([other_epc, same_rating])) == 2


def test_adtcl_141_keeps_pin_intents_separate_after_merge() -> None:
    description = """
Scenario: Solicitar PIN de seguridad (PIN correcto)
  When el usuario selecciona un evento de canal bloqueado
  Then se muestra pantalla para ingresar PIN de seguridad

Scenario: Solicitar PIN de seguridad para grabar un evento
  When el usuario selecciona Grabar
  Then se muestra pantalla para ingresar PIN de seguridad

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
    artifacts = _epic("ADTCL-141", "ADTCL-142", description=description)
    cases = candidates_from_jira_artifacts(artifacts, "rn.pdf", [], lambda *_a: None)
    actions = " ".join(step.action.lower() for row in cases for step in row.steps)
    assert "grabar" in actions
    assert "cancelar" in actions
    assert "favoritos" in actions
    assert "desbloquear" in actions
    assert len(cases) >= 5
    epcs = { (row.related_functionality or "").split("|")[0].strip() for row in cases }
    assert epcs == {"ADTCL-141"}


def test_adtcl_541_does_not_collapse_panel_into_one_tc() -> None:
    description = """
Scenario: Seleccionar botón Audio y Subtitulos en la botonera
  When el usuario selecciona el botón Audio y Subtítulos
  Then se muestra el Panel de Audio y Subtítulos
  And se pausa la reproducción del contenido

Scenario: Nueva selección de Audio
  When el usuario selecciona una opción de Audio
  Then se aplica el cambio de audio
  And aparece el check en la opción seleccionada

Scenario: Nueva selección de Subtitulos
  When el usuario selecciona una nueva opción de subtítulos
  Then se aplican los subtítulos
  And al seleccionar Desactivados se desactivan los subtítulos

Scenario: Cerrar Panel de Audio y Subtitulos si no hay interaccion
  When transcurren 5 segundos de inactividad
  Then se cierra automáticamente el Panel de Audio y Subtítulos
  And se reanuda la reproducción desde el punto pausado

Scenario: Comportamiento del RCU
  When el usuario presiona Back
  Then se cierra el Panel de Audio y Subtítulos
"""
    artifacts = _epic("ADTCL-541", "ADTCL-544", description=description)
    units = build_coverage_inventory(artifacts, "rn.pdf")
    cases = candidates_from_jira_artifacts(artifacts, "rn.pdf", [], lambda *_a: None)
    assert len(cases) < len(units) or len(cases) >= 4
    blob = " ".join(
        f"{row.name} {row.evidence or ''} "
        f"{' '.join(step.action + ' ' + step.expected_result for step in row.steps)}"
        for row in cases
    ).lower()
    assert "panel" in blob
    assert "audio" in blob
    assert "subt" in blob
    assert "back" in blob
    assert len(cases) >= 4


def test_adtcl_2394_back_digitacion_not_merged_with_back_idle() -> None:
    description = """
Scenario: Cancelar digitalización de canal
  Given hay digitación en curso
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
    artifacts = _epic("ADTCL-2394", "ADTCL-2396", description=description)
    cases = candidates_from_jira_artifacts(artifacts, "rn.pdf", [], lambda *_a: None)
    expected = " ".join(step.expected_result.lower() for row in cases for step in row.steps)
    assert "digit" in expected or "metadata" in expected
    assert "reproduc" in expected
    assert len(cases) >= 2


def test_adtcl_308_key_does_not_absorb_541_or_141() -> None:
    cases = apply_qc_rules(
        [
            _cand(
                name="No se logra obtener una llave",
                epic="ADTCL-308",
                action="El usuario ingresa al flujo correspondiente.",
                expected="El espacio de la leyenda muestra la llave",
                covers=["COV-308"],
            ),
            _cand(
                name="No se logra obtener una llave",
                epic="ADTCL-541",
                action="El usuario ingresa al flujo correspondiente.",
                expected="El espacio de la leyenda muestra la llave",
                covers=["COV-541"],
            ),
            _cand(
                name="No se logra obtener una llave",
                epic="ADTCL-141",
                action="El usuario ingresa al flujo correspondiente.",
                expected="El espacio de la leyenda muestra la llave",
                covers=["COV-141"],
            ),
        ]
    )
    assert len(cases) == 3
    assert {row.related_functionality for row in cases} == {"ADTCL-308", "ADTCL-541", "ADTCL-141"}


def test_ch_plus_repeat_can_merge_same_result() -> None:
    once = _cand(
        name="Cambiar al siguiente canal",
        epic="ADTCL-2394",
        action="El usuario presiona CH+",
        expected="El player cambia al siguiente canal contratado",
        covers=["COV-CH1"],
    )
    repeated = _cand(
        name="Cambiar al siguiente canal (CH+ repetido)",
        epic="ADTCL-2394",
        action="El usuario presiona CH+ repetido",
        expected="El player cambia al siguiente canal contratado",
        covers=["COV-CH2"],
    )
    minus = _cand(
        name="Cambiar al canal anterior",
        epic="ADTCL-2394",
        action="El usuario presiona CH-",
        expected="El player cambia al canal anterior contratado",
        covers=["COV-CH3"],
    )
    grouped = apply_qc_rules([once, repeated, minus])
    assert len(grouped) == 2
    covers = {tuple(sorted(row.covers)) for row in grouped}
    assert ("COV-CH1", "COV-CH2") in covers
    assert ("COV-CH3",) in covers
