"""Functional equivalence for CoverageUnit / candidate merge.

A Test Case may absorb many CoverageUnits only when epic, objective, user action,
functional condition, observable result and flow context all match after
normalization. Shared PIN, API, key or config text is not equivalence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.schemas.case_generation import CoverageUnit, GeneratedCaseCandidate
from app.services.executability import STABLE_GENERIC_STEP, is_stable_generic_step

_WS = re.compile(r"\s+")
_EPC = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")
_TECH = re.compile(
    r"\b(GET|POST|PUT|PATCH|DELETE)\b|"
    r"\bhttps?://\S+|"
    r"\bstatus codes?\b|\bHTTP\b|"
    r"\bmodule_version\b|"
    r"\bapa/metadata\b|"
    r"/[a-z][a-z0-9_\-/]{2,}",
    re.IGNORECASE,
)
_HTTP_CODE = re.compile(r"\b(?:status(?:\s*code)?|HTTP)\s*[:=]?\s*\d{3}\b|\b[1-5]\d{2}\b", re.I)
_RATING = re.compile(r"\b(no me gusta|me encanta|me gusta|like|dislike)\b", re.I)
_CONTENT_TYPE = re.compile(r"\b(series?|episodios?|temporadas?)\b", re.I)
_RESUME_POINT = re.compile(
    r"\bdesde (el )?(inicio|comienzo|ahora)\b|\bdesde el punto actual\b",
    re.I,
)
_RCU_REPEAT = re.compile(r"\b(ch\+|ch-)\s*(repetid[oa]|nuevamente|otra vez|de nuevo)\b", re.I)

_INTENT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("cancelar_grabacion", re.compile(r"cancelar grab", re.I)),
    ("eliminar_grabacion", re.compile(r"eliminar una grab|elimina(r)? (la )?grabaci", re.I)),
    ("grabar", re.compile(r"\bgrabar\b|bot[oó]n grabar", re.I)),
    ("eliminar_favorito", re.compile(r"eliminar.{0,24}favorit|quita.{0,24}favorit", re.I)),
    ("agregar_favorito", re.compile(r"favorit", re.I)),
    ("desbloquear", re.compile(r"desbloque", re.I)),
    ("reproducir_grabacion", re.compile(r"reproducir una grab|al reproducir (una )?grab", re.I)),
    ("reproducir_bloqueado", re.compile(r"(evento|canal) bloquead", re.I)),
    ("reproducir", re.compile(r"\breproducir\b", re.I)),
    ("abrir_panel", re.compile(r"abre(r)? el panel|muestra el panel|bot[oó]n audio", re.I)),
    ("pausar", re.compile(r"pausa(r)? (la )?reproduc", re.I)),
    ("seleccionar_audio", re.compile(r"opci[oó]n de audio|seleccion\w*.{0,20}audio|cambio de audio", re.I)),
    ("seleccionar_subtitulo", re.compile(r"opci[oó]n de subt|seleccion\w*.{0,20}subt", re.I)),
    ("desactivar_subtitulos", re.compile(r"desactiv", re.I)),
    ("check_seleccion", re.compile(r"\bcheck\b", re.I)),
    ("panel_permanece", re.compile(r"permanece (abierto|desplegado)", re.I)),
    ("cerrar_timeout", re.compile(r"inactividad|cierra autom[aá]ticamente|\btimeout\b|5 segundos", re.I)),
    ("reanudar", re.compile(r"reanud", re.I)),
    ("back", re.compile(r"\bback\b", re.I)),
    ("siguiente_canal", re.compile(r"\bch\+|siguiente canal|flecha derecha|\bderecha\b", re.I)),
    ("canal_anterior", re.compile(r"\bch-|canal anterior|flecha izquierda|\bizquierda\b", re.I)),
    ("ok", re.compile(r"\bok\b", re.I)),
    ("calificar", re.compile(r"calific|me gusta|me encanta|no me gusta", re.I)),
    ("legend_missing", re.compile(r"no se logra obtener una llave|mostrar(se)? la llave", re.I)),
    ("legend_empty", re.compile(r"llave se encuentra vac|quedar vac", re.I)),
    ("aceptar_consentimiento", re.compile(r"\baceptar\b|registra(r)? (el )?consentimiento", re.I)),
    ("nueva_politica", re.compile(r"nueva versi[oó]n|policy_version|cambien las pol[ií]ticas", re.I)),
    ("redirigir_politica", re.compile(r"redirig|pol[ií]tica (completa )?de cookies|policy_url", re.I)),
    ("ocultar_banner", re.compile(r"no (se )?(debe )?mostrar.{0,40}banner|banner.{0,40}no se (debe )?muestra", re.I)),
    ("mostrar_banner", re.compile(r"mostrar.{0,40}banner|banner.{0,40}muestra", re.I)),
    ("primer_acceso", re.compile(r"primer acceso|por default|primera vez", re.I)),
    ("ultimo_canal", re.compile(r"[uú]ltimo canal", re.I)),
    ("digitacion", re.compile(r"digit", re.I)),
    ("punto_reproduccion", re.compile(r"desde (el )?(inicio|ahora)|desde el punto actual", re.I)),
    ("ingresar_pin", re.compile(r"ingresa(r)? pin|\bpin de seguridad\b", re.I)),
]

_FLOW_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("pin", re.compile(r"\bpin\b|parental", re.I)),
    ("audio_subtitulos", re.compile(r"audio y subt|panel de audio|subt[ií]tul", re.I)),
    ("tv_vivo", re.compile(r"tv en vivo|cambio de canal|digitaci[oó]n de canal", re.I)),
    ("leyenda", re.compile(r"leyenda|no se logra obtener una llave|llave se encuentra vac", re.I)),
    ("cookies", re.compile(r"banner|consentimiento|cookies|pol[ií]tica de cookies", re.I)),
    ("calificacion", re.compile(r"calific|me gusta|me encanta", re.I)),
    ("reproduccion", re.compile(r"reproduc|player|vod", re.I)),
]


@dataclass(frozen=True)
class FunctionalEquivalenceKey:
    epic: str
    objective: str
    user_action: str
    condition: str
    observable: str
    flow_context: str

    def value(self) -> str:
        return "|".join(
            (
                self.epic,
                self.objective,
                self.user_action,
                self.condition,
                self.observable,
                self.flow_context,
            )
        )


def _squash(text: str) -> str:
    return _WS.sub(" ", (text or "").strip().lower())


def normalize_for_equivalence(text: str) -> str:
    """Drop technical noise and synonym variants that are not functional differences."""
    cleaned = _TECH.sub(" ", text or "")
    cleaned = _HTTP_CODE.sub(" ", cleaned)
    cleaned = _RCU_REPEAT.sub(lambda match: match.group(1), cleaned)
    cleaned = _RATING.sub("calificacion", cleaned)
    cleaned = _CONTENT_TYPE.sub("contenido", cleaned)
    cleaned = _RESUME_POINT.sub("punto_reproduccion", cleaned)
    cleaned = _squash(cleaned)
    cleaned = cleaned.replace("á", "a").replace("é", "e").replace("í", "i")
    cleaned = cleaned.replace("ó", "o").replace("ú", "u").replace("ü", "u")
    cleaned = cleaned.replace("ñ", "n")
    return cleaned.strip(" .;:-")


def normalize_observable_text(text: str) -> str:
    return normalize_for_equivalence(text)


def _epic_of(source: CoverageUnit | GeneratedCaseCandidate) -> str:
    if isinstance(source, CoverageUnit):
        raw = source.rn_key or source.artifact_key or ""
    else:
        raw = source.related_functionality or ""
    match = _EPC.search(raw or "")
    if match:
        return match.group(1).upper()
    return _squash(raw).upper()


def _blob(source: CoverageUnit | GeneratedCaseCandidate) -> str:
    if isinstance(source, CoverageUnit):
        return " ".join(
            part
            for part in (
                source.scenario,
                source.behavior,
                source.test_intent,
                source.user_action,
                " ".join(source.observable_then or []),
                source.body,
                source.special_condition,
                source.condition_b,
            )
            if part
        )
    steps = " ".join(f"{step.action} {step.expected_result}" for step in source.steps)
    return " ".join(
        part
        for part in (
            source.description,
            source.evidence,
            source.name,
            source.precondition,
            steps,
            source.test_data,
        )
        if part
    )


def _intent_context(source: CoverageUnit | GeneratedCaseCandidate) -> str:
    """Scenario name, Given/And, flow context. Not the rewritten Expected or shared AC vocab."""
    if isinstance(source, CoverageUnit):
        return " ".join(
            part
            for part in (
                source.scenario,
                source.test_intent,
                source.body,
                source.special_condition,
                source.condition_b,
            )
            if part
        )
    steps = " ".join(step.action for step in source.steps if step.action)
    return " ".join(
        part
        for part in (source.name, source.evidence, source.precondition, steps)
        if part
    )


def _primary_title(source: CoverageUnit | GeneratedCaseCandidate) -> str:
    if isinstance(source, CoverageUnit):
        return source.scenario or source.test_intent or ""
    evid = (source.evidence or "").split("\n", 1)[0]
    return evid or source.name or ""


def _intent_token(text: str) -> str:
    normalized = normalize_for_equivalence(text)
    matches: list[str] = []
    for token, pattern in _INTENT_PATTERNS:
        if pattern.search(text or "") or pattern.search(normalized):
            matches.append(token)
    if not matches:
        return ""
    skip = {"ingresar_pin", "reproducir_bloqueado"}
    specific = [token for token in matches if token not in skip]
    return (specific or matches)[0]


def _flow_context(text: str) -> str:
    for token, pattern in _FLOW_PATTERNS:
        if pattern.search(text):
            return token
    return "general"


def _user_action_of(source: CoverageUnit | GeneratedCaseCandidate) -> str:
    if isinstance(source, CoverageUnit):
        raw = source.user_action or ""
    else:
        raw = source.steps[0].action if source.steps else ""
    if not raw or is_stable_generic_step(raw) or raw.strip() == STABLE_GENERIC_STEP:
        derived = _intent_token(_primary_title(source)) or _intent_token(_intent_context(source))
        context = normalize_for_equivalence(_primary_title(source) or _intent_context(source))[:120]
        return f"sin_accion:{derived or context}"
    normalized = normalize_for_equivalence(raw)
    intent = _intent_token(raw)
    if intent in {
        "grabar",
        "cancelar_grabacion",
        "agregar_favorito",
        "eliminar_favorito",
        "desbloquear",
        "back",
        "siguiente_canal",
        "canal_anterior",
        "ok",
        "seleccionar_audio",
        "seleccionar_subtitulo",
        "abrir_panel",
        "calificar",
        "ingresar_pin",
    }:
        return intent
    return normalized


_FUNCTIONAL_VARIANT = re.compile(
    r"\b(plan|add-?on|paquete|producto|visibilidad)\s*=",
    re.IGNORECASE,
)


def _condition_of(source: CoverageUnit | GeneratedCaseCandidate) -> str:
    if isinstance(source, CoverageUnit):
        raw = " ".join(
            part
            for part in (
                source.special_condition,
                source.condition_b,
                source.normal_precondition,
            )
            if part
        )
        extra = source.extra_test_data or ""
        if extra and (
            "Example funcional" in extra or _FUNCTIONAL_VARIANT.search(extra) or "visibilidad=" in extra
        ):
            raw = f"{raw} {extra}"
    else:
        raw = source.precondition or ""
        extra = source.test_data or ""
        if extra and _FUNCTIONAL_VARIANT.search(extra):
            raw = f"{raw} {extra}"
    return normalize_for_equivalence(raw)


def _observable_of(source: CoverageUnit | GeneratedCaseCandidate) -> str:
    if isinstance(source, CoverageUnit):
        raw = " ".join(source.observable_then or [])
    else:
        raw = " ".join(step.expected_result for step in source.steps)
    return normalize_for_equivalence(raw)


def _objective_of(source: CoverageUnit | GeneratedCaseCandidate, blob: str, observable: str) -> str:
    context = _intent_context(source)
    token = _intent_token(_primary_title(source)) or _intent_token(context)
    if token:
        return token
    if isinstance(source, CoverageUnit):
        title = " ".join(part for part in (source.test_intent, source.scenario, source.behavior) if part)
    else:
        title = source.description or source.name or ""
    token = _intent_token(title) or _intent_token(blob)
    if token and token != "ingresar_pin":
        return token
    if token == "ingresar_pin" and _intent_token(context):
        return _intent_token(context)
    if token:
        return token
    return (observable or normalize_for_equivalence(title or context))[:160]


def build_functional_equivalence_key(
    source: CoverageUnit | GeneratedCaseCandidate,
) -> FunctionalEquivalenceKey:
    blob = _blob(source)
    observable = _observable_of(source)
    return FunctionalEquivalenceKey(
        epic=_epic_of(source),
        objective=_objective_of(source, blob, observable),
        user_action=_user_action_of(source),
        condition=_condition_of(source),
        observable=observable,
        flow_context=_flow_context(blob),
    )


def functionally_equivalent(left: Any, right: Any) -> bool:
    return build_functional_equivalence_key(left) == build_functional_equivalence_key(right)
