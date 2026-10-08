"""FASE 5 / 5.1: LLM generation contract (prompt + covered_unit_ids + fidelity)."""

from app.schemas.case_generation import CandidateStep, CoverageUnit, GeneratedCaseCandidate
from app.services.ai_case_engine import (
    _ENGINE_RULES,
    _JSON_INSTRUCTIONS,
    _parse_llm_candidates,
    enforce_llm_unit_fidelity,
)
from app.services.executability import STABLE_GENERIC_STEP


def test_prompt_requires_covered_unit_ids_and_functional_merge() -> None:
    blob = _ENGINE_RULES + "\n" + _JSON_INSTRUCTIONS
    assert "covered_unit_ids" in blob
    assert "covered_unit_ids es obligatorio" in blob
    assert "Grabar ≠ Cancelar" in blob or "Grabar≠Cancelar" in blob
    assert "Grabar ≠ Eliminar" in blob or "Grabar≠Eliminar" in blob
    assert "Reproducir ≠ Grabar" in blob or "Reproducir≠Grabar" in blob
    assert "Agregar favorito" in blob and "Eliminar favorito" in blob
    assert "Seleccionar ≠ Back" in blob or "Seleccionar≠Back" in blob
    assert "Audio ≠ Subtítulo" in blob or "Audio≠Subtítulo" in blob
    assert "cambio de pista" in blob or "pista/track" in blob
    assert "El mismo Expected NO es suficiente" in blob or "El mismo Expected NO justifica" in blob
    assert "Se observa el comportamiento definido." in blob
    assert "Las únicas fuentes permitidas para generar casos mediante LLM" in _ENGINE_RULES
    assert "Ignora NCO, TRI, QA Bugs y QC Bugs" in _ENGINE_RULES


def test_parse_covered_unit_ids_into_covers() -> None:
    parsed = _parse_llm_candidates(
        {
            "candidates": [
                {
                    "name": "Grabar evento bloqueado",
                    "description": "PIN al grabar",
                    "steps": [
                        {
                            "step_number": 1,
                            "action": "El usuario selecciona Grabar programa",
                            "expected_result": "Se muestra la pantalla de PIN",
                        }
                    ],
                    "evidence": "ADTCL-141",
                    "justification": "LLM",
                    "related_functionality": "ADTCL-141",
                    "related_jira": "ADTCL-157",
                    "confidence": "high",
                    "review_required": True,
                    "basic_validation": False,
                    "covered_unit_ids": ["COV-118"],
                }
            ]
        },
        [],
    )
    assert parsed
    assert parsed[0].covered_unit_ids == ["COV-118"]
    assert parsed[0].covers == ["COV-118"]


def test_parse_covers_alias_still_accepted() -> None:
    parsed = _parse_llm_candidates(
        {
            "candidates": [
                {
                    "name": "Cancelar grabación",
                    "description": "PIN al cancelar",
                    "steps": [
                        {
                            "step_number": 1,
                            "action": "El usuario selecciona Cancelar grabación",
                            "expected_result": "Se muestra la pantalla de PIN",
                        }
                    ],
                    "evidence": "ADTCL-141",
                    "justification": "LLM",
                    "related_functionality": "ADTCL-141",
                    "confidence": "high",
                    "review_required": True,
                    "basic_validation": False,
                    "covers": ["COV-120"],
                }
            ]
        },
        [],
    )
    assert parsed[0].covers == ["COV-120"]
    assert parsed[0].covered_unit_ids == ["COV-120"]


def test_coverage_unit_for_llm_includes_user_action() -> None:
    payload = CoverageUnit(
        coverage_id="COV-001",
        role="A",
        behavior="Grabar",
        scenario="Grabar evento",
        evidence="When selecciona Grabar",
        test_intent="grabar",
        user_action="El usuario selecciona Grabar programa",
    ).for_llm()
    assert payload["user_action"] == "El usuario selecciona Grabar programa"
    assert payload["coverage_id"] == "COV-001"
    assert "body" not in payload


def _unit(**kwargs) -> CoverageUnit:
    payload = {
        "coverage_id": "COV-008",
        "role": "A",
        "behavior": "Panel",
        "scenario": "Visualizar pantalla de Panel de Más Información",
        "evidence": "When El usuario selecciona Más Opciones",
        "test_intent": "abrir panel",
    }
    payload.update(kwargs)
    return CoverageUnit(**payload)


def _cand(*, action: str, expected: str, covers: list[str]) -> GeneratedCaseCandidate:
    return GeneratedCaseCandidate(
        name="TC",
        description="TC",
        steps=[CandidateStep(step_number=1, action=action, expected_result=expected)],
        evidence="e",
        justification="LLM",
        related_functionality="ADTCL-308",
        covers=covers,
        covered_unit_ids=covers,
        generation_origin="llm",
    )


def test_prompt_forbids_wrong_when_and_user_action_expected() -> None:
    blob = _ENGINE_RULES + "\n" + _JSON_INSTRUCTIONS
    assert "Más Opciones" in blob
    assert "Nunca una acción del usuario" in blob or "NUNCA describe una acción del usuario" in blob
    assert "El usuario selecciona la opción." in blob


def test_fidelity_rewrites_wrong_when_to_unit_user_action() -> None:
    unit = _unit(user_action='El usuario selecciona "Más Opciones".')
    cand = _cand(
        action='El usuario selecciona la opción “Grabar programa” o “Cancelar grabación” desde el Panel de Más Información.',
        expected="Se muestran las opciones del panel",
        covers=["COV-008"],
    )
    out = enforce_llm_unit_fidelity([cand], [unit])
    assert out
    assert out[0].steps[0].action == 'El usuario selecciona "Más Opciones".'
    assert out[0].covered_unit_ids == ["COV-008"]


def test_fidelity_replaces_invented_action_when_user_action_empty() -> None:
    unit = _unit(
        coverage_id="COV-012",
        user_action=None,
        scenario="se muestra la pantalla solicitando el PIN para desbloquear canal",
        evidence="Then se muestra la pantalla solicitando el PIN",
    )
    cand = _cand(
        action="Seleccionar un canal bloqueado y solicitar desbloquearlo.",
        expected="Se muestra la pantalla de PIN",
        covers=["COV-012"],
    )
    out = enforce_llm_unit_fidelity([cand], [unit])
    assert out
    assert out[0].steps[0].action == STABLE_GENERIC_STEP


def test_fidelity_replaces_expected_that_is_user_action() -> None:
    unit = _unit(
        coverage_id="COV-032",
        user_action="El usuario ingresa correctamente el PIN de seguridad para grabar una serie.",
        observable_then=["Se inicia la grabación de la serie"],
        scenario="Iniciar grabación de una serie completa",
    )
    cand = _cand(
        action="El usuario ingresa correctamente el PIN de seguridad para grabar una serie.",
        expected="el usuario selecciona la opción",
        covers=["COV-032"],
    )
    out = enforce_llm_unit_fidelity([cand], [unit])
    assert out
    assert not out[0].steps[0].expected_result.lower().startswith("el usuario")
    assert "grabación" in out[0].steps[0].expected_result.lower()


def test_fidelity_drops_ids_when_when_does_not_represent_unit() -> None:
    grabar = _unit(
        coverage_id="COV-A",
        user_action="El usuario selecciona Grabar programa",
        scenario="Grabar",
    )
    cancelar = _unit(
        coverage_id="COV-B",
        user_action="El usuario selecciona Cancelar grabación",
        scenario="Cancelar",
    )
    cand = _cand(
        action="El usuario selecciona Grabar programa",
        expected="Se muestra la pantalla de PIN",
        covers=["COV-A", "COV-B"],
    )
    out = enforce_llm_unit_fidelity([cand], [grabar, cancelar])
    assert out
    assert out[0].covered_unit_ids == ["COV-A"]
    assert out[0].covers == ["COV-A"]


def test_fidelity_keeps_functionally_equivalent_same_action() -> None:
    left = _unit(
        coverage_id="COV-A",
        user_action="El usuario selecciona un evento en vivo",
        observable_then=["Se muestra la alerta"],
        scenario="Alerta en vivo",
    )
    right = _unit(
        coverage_id="COV-B",
        user_action="El usuario selecciona un evento en vivo",
        observable_then=["Se muestra la alerta"],
        scenario="Alerta rating",
    )
    cand = _cand(
        action="El usuario selecciona un evento en vivo",
        expected="Se muestra la alerta",
        covers=["COV-A", "COV-B"],
    )
    out = enforce_llm_unit_fidelity([cand], [left, right])
    assert out[0].covered_unit_ids == ["COV-A", "COV-B"]


def test_fidelity_rejects_grabar_vs_eliminar() -> None:
    grabar = _unit(
        coverage_id="COV-A",
        user_action="El usuario selecciona Grabar programa",
        scenario="Grabar",
    )
    eliminar = _unit(
        coverage_id="COV-B",
        user_action="El usuario intenta eliminar una grabación",
        scenario="Eliminar grabación",
    )
    cand = _cand(
        action="El usuario selecciona Grabar programa",
        expected="Se muestra PIN",
        covers=["COV-A", "COV-B"],
    )
    out = enforce_llm_unit_fidelity([cand], [grabar, eliminar])
    assert out[0].covered_unit_ids == ["COV-A"]


def test_fidelity_rejects_reproducir_vs_grabar() -> None:
    reproducir = _unit(
        coverage_id="COV-A",
        user_action="El usuario intenta reproducir una grabación",
        scenario="Reproducir",
    )
    grabar = _unit(
        coverage_id="COV-B",
        user_action="El usuario intenta grabar un evento",
        scenario="Grabar",
    )
    cand = _cand(
        action="El usuario intenta reproducir una grabación",
        expected="Se muestra PIN",
        covers=["COV-A", "COV-B"],
    )
    out = enforce_llm_unit_fidelity([cand], [reproducir, grabar])
    assert out[0].covered_unit_ids == ["COV-A"]


def test_fidelity_rejects_agregar_vs_eliminar_favorito() -> None:
    agregar = _unit(
        coverage_id="COV-A",
        user_action="El usuario selecciona Añadir canal a favoritos",
        scenario="Agregar favorito",
    )
    eliminar = _unit(
        coverage_id="COV-B",
        user_action="El usuario selecciona Quitar de favoritos",
        scenario="Eliminar favorito",
    )
    cand = _cand(
        action="El usuario selecciona Añadir canal a favoritos",
        expected="Se muestra PIN",
        covers=["COV-A", "COV-B"],
    )
    out = enforce_llm_unit_fidelity([cand], [agregar, eliminar])
    assert out[0].covered_unit_ids == ["COV-A"]


def test_fidelity_rejects_audio_vs_subtitulo_when_actions_differ() -> None:
    audio = _unit(
        coverage_id="COV-A",
        user_action="El usuario selecciona una pista de audio",
        scenario="Cambio de audio",
    )
    sub = _unit(
        coverage_id="COV-B",
        user_action="El usuario selecciona una pista de subtítulos",
        scenario="Cambio de subtítulos",
    )
    cand = _cand(
        action="El usuario selecciona una pista de audio",
        expected="Se aplica el cambio",
        covers=["COV-A", "COV-B"],
    )
    out = enforce_llm_unit_fidelity([cand], [audio, sub])
    assert out[0].covered_unit_ids == ["COV-A"]


def test_fidelity_allows_same_track_change_variant() -> None:
    shared = "El usuario selecciona una pista de audio o una pista de subtítulos"
    left = _unit(
        coverage_id="COV-A",
        user_action=shared,
        observable_then=["No se afecta la reproducción"],
        scenario="Error de cambio de pista audio",
    )
    right = _unit(
        coverage_id="COV-B",
        user_action=shared,
        observable_then=["No se afecta la reproducción"],
        scenario="Error de cambio de pista subtítulos",
    )
    cand = _cand(
        action=shared,
        expected="No se afecta la reproducción",
        covers=["COV-A", "COV-B"],
    )
    out = enforce_llm_unit_fidelity([cand], [left, right])
    assert out[0].covered_unit_ids == ["COV-A", "COV-B"]


def test_fidelity_drops_candidate_without_covered_unit_ids() -> None:
    unit = _unit(coverage_id="COV-A", user_action="El usuario selecciona Grabar programa")
    cand = _cand(
        action="El usuario selecciona Grabar programa",
        expected="Se muestra PIN",
        covers=[],
    )
    cand.covered_unit_ids = []
    out = enforce_llm_unit_fidelity([cand], [unit])
    assert out == []
