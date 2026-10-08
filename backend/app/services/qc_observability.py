"""Second decision after A–G: is this Scenario QC-relevant for an end user?

A–G describes Gherkin structure. This module decides whether QC can prepare,
execute and observe a differentiated experience. Technical verbs (renderiza,
oculta, habilita el renderizado) do not by themselves exclude QC coverage.
Unstated screens or actions are not invented.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from app.services.executability import STABLE_GENERIC_STEP

QcRelevance = Literal[
    "QC_FUNCTIONAL",
    "QC_REGRESSION",
    "QC_VARIANT",
    "CONFIG_ONLY",
    "IMPLEMENTATION_ONLY",
    "AMBIGUOUS",
]

_USER_ACTION = re.compile(
    r"\b(el usuario|usuario)\b.{0,80}\b(hace scroll|scroll|selecciona|ingresa|"
    r"abre|navega|pulsa|presiona|clic|entra|visualiza)\b|"
    r"\b(hace scroll|scroll hacia)\b|"
    r"\b(bot[oó]n ok|bot[oó]n back|flecha de navegaci[oó]n|remote control|rcu)\b",
    re.IGNORECASE,
)
_SCROLL = re.compile(r"\bscroll\b", re.IGNORECASE)
_RENDER = re.compile(
    r"\b((no se )?(renderiza|renderizar)|habilita el renderizado|"
    r"se habilita el renderizado|el renderizado de)\b",
    re.IGNORECASE,
)
_HIDE_SHOW = re.compile(
    r"\b(se oculta|se debe ocultar|debe ocultarse|permanece oculto|"
    r"no se presenta|se superpone|transiciona|desaparece|aparece|"
    r"se muestra|no se muestra|se visualiza|deja de visualizarse|"
    r"deja de mostrarse|conserva su comportamiento|se mantiene el comportamiento|"
    r"no altera la estructura|regresa a su estado|estado inicial|"
    r"estado s[oó]lido)\b",
    re.IGNORECASE,
)
_SURFACE = re.compile(
    r"\b(background(?: comercial)?|brandheader|highlight|super destacado|"
    r"gradient(?:o)?(?: din[aá]mico)?|header|home|pantalla|banner|modal|"
    r"bot[oó]n|player|carrusel|men[uú]|ticket|layout|leyenda|fondo comercial|"
    r"componente|pip|calificaci[oó]n|cr[eé]ditos|outline|vcard|fin player|"
    r"notificaci[oó]n|contador)\b",
    re.IGNORECASE,
)
_CONFIG_THEN = re.compile(
    r"\b(se aplica el valor|objeto ['\"]default['\"]|enabled['\"]?|"
    r"configuraci[oó]n (por defecto|default|remota)|feature flag|"
    r"module_version)\b",
    re.IGNORECASE,
)
_DEFINITION = re.compile(
    r"\bse considera que\b|\bno existe super destacado\b",
    re.IGNORECASE,
)
_IMPLEMENTATION = re.compile(
    r"\b(llave resuelta|hardcodeada|hardcode|no se persiste|no se persist|"
    r"trace_id|pipeline|schema|apa/metadata|query param|"
    r"ninguna url de asset|archivo persistido|espacio de color|srgb|"
    r"vp9|webm|codec|hilo de background)\b",
    re.IGNORECASE,
)
_REGRESSION = re.compile(
    r"conserva(r)? su comportamiento actual|"
    r"se mantiene el comportamiento( actual)?|"
    r"no altera la estructura|"
    r"sin efecto fuera",
    re.IGNORECASE,
)
_FLAG_OFF = re.compile(
    r"\b(enabled['\"]?\s*(resuelve en )?false|deshabilitad[oa]|"
    r"funcionalidad deshabilitada|flag (off|deshabilitado))\b",
    re.IGNORECASE,
)
_INVENT = re.compile(
    r"recorre la experiencia cuando|recorre el flujo de la funcionalidad",
    re.IGNORECASE,
)


@dataclass
class QcObservability:
    kind: QcRelevance
    condition: str | None = None
    user_action: str | None = None
    observables: list[str] = field(default_factory=list)
    reason: str = ""


def translate_then_to_observable(clause: str) -> str | None:
    """Map a technical Then to a user-visible statement only when the Then already names it."""
    text = re.sub(r"\s+", " ", (clause or "").strip())
    if not text:
        return None
    lowered = text.lower()
    if _IMPLEMENTATION.search(text) and not _HIDE_SHOW.search(text) and not _RENDER.search(text):
        return None
    if _DEFINITION.search(text) and not _SURFACE.search(text) and not _RENDER.search(text):
        return None
    if _CONFIG_THEN.search(text) and not _HIDE_SHOW.search(text) and not _RENDER.search(text):
        return None

    negated_render = bool(re.search(r"\bno se renderiza\b", lowered))
    enabled_render = bool(re.search(r"habilita el renderizado|se habilita el renderizado", lowered))
    positive_render = bool(re.search(r"\bse renderiza\b", lowered)) and not negated_render
    hidden = bool(
        re.search(
            r"\bse oculta\b|\bse debe ocultar\b|\bdebe ocultarse\b|"
            r"\bno se presenta\b|\bpermanece oculto\b|\bdesaparece\b|"
            r"\bdeja de visualizarse\b|\bdeja de mostrarse\b",
            lowered,
        )
    )
    shown = bool(re.search(r"\bse muestra\b|\bse visualiza\b|\baparece\b", lowered))
    overlay = bool(re.search(r"\bse superpone\b|\btransiciona\b", lowered))
    keeps = bool(_REGRESSION.search(text))

    surface_match = _SURFACE.search(text)
    surface = surface_match.group(0) if surface_match else None

    if negated_render and surface:
        return f"No se muestra {surface}."
    if enabled_render and surface:
        return f"Se muestra {surface}."
    if positive_render and surface:
        return f"Se muestra {surface}."
    if hidden and surface:
        return f"No se muestra {surface}."
    if shown:
        return text.rstrip(".") + "."
    if overlay and surface:
        return f"Se observa el cambio visual de {surface}."
    if re.search(r"regresa a su estado|estado inicial|estado s[oó]lido", lowered) and surface:
        return f"Se observa el cambio visual de {surface}."
    if keeps:
        return "Se mantiene el comportamiento actual."
    if _HIDE_SHOW.search(text) and surface:
        return text.rstrip(".") + "."
    return None


def extract_qc_observables(then: list[str], title: str = "") -> list[str]:
    found: list[str] = []
    for clause in then:
        mapped = translate_then_to_observable(clause)
        if mapped and mapped not in found:
            found.append(mapped)
    if not found and then:
        mapped = translate_then_to_observable(" ".join(then))
        if mapped:
            found.append(mapped)
    if not found and title:
        mapped = translate_then_to_observable(title)
        if mapped:
            found.append(mapped)
    return found


def extract_user_action(when: list[str], title: str, body: str, given: list[str] | None = None) -> str | None:
    sources = list(when or [])
    for clause in sources:
        if _INVENT.search(clause or ""):
            continue
        if _USER_ACTION.search(clause) or _SCROLL.search(clause):
            action = clause.strip()
            if action:
                if action[0].islower():
                    action = action[0].upper() + action[1:]
                if not action.endswith("."):
                    action += "."
                return action
    blob = f"{title}\n{body}"
    if _SCROLL.search(blob) and (_USER_ACTION.search(blob) or "el usuario hace scroll" in blob.lower()):
        return "El usuario hace scroll."
    for clause in list(given or []):
        if _INVENT.search(clause or ""):
            continue
        if _USER_ACTION.search(clause):
            action = clause.strip()
            if action[0].islower():
                action = action[0].upper() + action[1:]
            if not action.endswith("."):
                action += "."
            return action
    return None


def _is_implementation_only(then: list[str], title: str) -> bool:
    blob = f"{title} {' '.join(then)}"
    if extract_qc_observables(then, title):
        return False
    return bool(_IMPLEMENTATION.search(blob) or _DEFINITION.search(blob) and not _SURFACE.search(blob))


def classify_qc_observability(
    title: str,
    body: str,
    *,
    role: str,
    observable_then: list[str] | None = None,
    given: list[str] | None = None,
    when: list[str] | None = None,
    then: list[str] | None = None,
) -> QcObservability:
    given = list(given or [])
    when = list(when or [])
    then = list(then or [])
    condition = "; ".join(part for part in given if part) or (title.strip() or None)
    user_action = extract_user_action(when, title, body, given=given)
    observables = list(observable_then or [])
    translated = extract_qc_observables(then, title)
    for item in translated:
        if item not in observables:
            observables.append(item)

    if role in {"D", "E", "F"}:
        return QcObservability(
            kind="IMPLEMENTATION_ONLY",
            condition=condition,
            user_action=user_action,
            observables=[],
            reason="Métrica, proceso QA o fuera de alcance; no es QC de experiencia.",
        )
    if role == "B":
        if observables:
            return QcObservability(
                kind="QC_VARIANT",
                condition=condition,
                user_action=user_action or STABLE_GENERIC_STEP,
                observables=observables,
                reason="Variante/dato del mismo comportamiento; se conserva como cobertura.",
            )
        return QcObservability(
            kind="QC_VARIANT" if re.search(r"llave", title, re.I) else "CONFIG_ONLY",
            condition=condition,
            user_action=user_action,
            observables=[],
            reason="Condición o llave de soporte sin resultado observable propio.",
        )

    if not then and not observables:
        return QcObservability(
            kind="AMBIGUOUS",
            condition=condition,
            user_action=user_action,
            reason="Then vacío; no se inventa un resultado.",
        )

    blob = f"{title} {' '.join(then)}"
    if _DEFINITION.search(blob) and not extract_qc_observables(then, title):
        return QcObservability(
            kind="QC_VARIANT",
            condition=condition,
            user_action=user_action,
            observables=[],
            reason="Define una condición interna del mismo comportamiento; no es TC propio.",
        )
    if _CONFIG_THEN.search(blob) and not extract_qc_observables(then, title) and not _RENDER.search(blob):
        return QcObservability(
            kind="CONFIG_ONLY",
            condition=condition,
            user_action=user_action,
            observables=[],
            reason="Solo aplica configuración; no describe experiencia.",
        )
    if _is_implementation_only(then, title) and not observables:
        return QcObservability(
            kind="IMPLEMENTATION_ONLY",
            condition=condition,
            user_action=user_action,
            observables=[],
            reason="Detalle técnico sin consecuencia funcional para el usuario.",
        )

    if not observables:
        return QcObservability(
            kind="AMBIGUOUS",
            condition=condition,
            user_action=user_action,
            reason="No hay consecuencia observable respaldada por el Then.",
        )

    kind: QcRelevance = "QC_REGRESSION" if _REGRESSION.search(blob) else "QC_FUNCTIONAL"
    if _FLAG_OFF.search(blob) and observables:
        kind = "QC_FUNCTIONAL"
    return QcObservability(
        kind=kind,
        condition=condition,
        user_action=user_action or STABLE_GENERIC_STEP,
        observables=observables,
        reason="QC puede preparar la condición, ejecutar y observar un resultado diferenciable.",
    )


def is_qc_coverage(obs: QcObservability) -> bool:
    return obs.kind in {"QC_FUNCTIONAL", "QC_REGRESSION"}
