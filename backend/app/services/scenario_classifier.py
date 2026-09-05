"""Classify a Jira Gherkin Scenario by the kind of information it represents.

Classification is driven by the meaning of the Then (and the title when the Then
is silent), not by a banned-word list. A technical When with an observable Then
is G, not C.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from app.schemas.case_generation import GenerationStats

ScenarioRole = Literal["A", "B", "C", "D", "E", "F", "G"]

_GIVEN = re.compile(r"^\s*(Given|Dado que|Dado|And|Y|Pero|But)\s+", re.IGNORECASE)
_WHEN = re.compile(r"^\s*(When|Cuando)\s+", re.IGNORECASE)
_THEN = re.compile(r"^\s*(Then|Entonces)\s+", re.IGNORECASE)
_STEP = re.compile(r"^\s*(Given|Dado que|Dado|When|Cuando|Then|Entonces|And|Y|Pero|But)\s+", re.I)

_OUT_OF_SCOPE = re.compile(
    r"fuera de alcance|no se entrega|no entregad|out of scope|won'?t be delivered|"
    r"no forma parte del entregable|no aplica (en|para) (este|esta) (release|entregable)|"
    r"alcance expl[ií]citamente no entregado",
    re.IGNORECASE,
)
_QA_PROCESS = re.compile(
    r"desviaci[oó]n de nomenclatura|correcci[oó]n de desviaci[oó]n|"
    r"habilita el despliegue|reporta antes del despliegue|proceso de QA|"
    r"checklist de QA|sign[- ]off de (qa|desarrollo)",
    re.IGNORECASE,
)
_METRICS = re.compile(
    r"\b(m[eé]tric|analytics|anal[ií]tica|ga4|firebase|\bdat\b|tracking|"
    r"pipeline|schema|esquema de m[eé]tricas|instrument|"
    r"payment_method_selected|checkout_start|checkout_success|checkout_error|"
    r"nomenclatura DAT|evento de (selecci[oó]n|anal|inicio de checkout|error de pago|[eé]xito de pago)|"
    r"env[ií]o de m[eé]trica|metrica de visualizaci|telemetr)",
    re.IGNORECASE,
)
_NO_BLOCK_UX = re.compile(
    r"no bloquea|no se bloquea|sin bloquear|puede completar el pago|"
    r"contin[uú]a (a |en )?(la )?(home|experiencia)|"
    r"permanece en (claro|la experiencia|home)|navegaci[oó]n",
    re.IGNORECASE,
)
_PRODUCT_UI = re.compile(
    r"\b(banner|spotlight|modal|qr|[ií]tem|tarjeta|marcador|gol|alineaci|"
    r"mini ?player|home|men[uú]|paypal|pago|player|carrusel|partido|"
    r"live ?feed|feed)\b",
    re.IGNORECASE,
)
_STATE_CHANGE = re.compile(
    r"\b(actualiza|muestra|mostrar|oculta|cierra|cierre|abre|ve |visualiza|"
    r"reproduce|llega|sale |ingresa|dispara|aparece|desaparece|"
    r"habilit|deshabilit|no se muestra|se muestra|no listo|est[aá] listo|"
    r"una sola vez|finalizaci[oó]n|selecciona|posponer)\b",
    re.IGNORECASE,
)
_USER_OR_UI = re.compile(
    r"\b(usuario|user|banner|modal|qr|c[oó]digo qr|[ií]tem|pesta[nñ]a|bot[oó]n|"
    r"pantalla|home|men[uú]|player|mini ?player|tarjeta|carrusel|vcard|"
    r"mensaje|error (en|de|visible)|pago|paypal|checkout|reproducci[oó]n|"
    r"live ?feed|marcador|alineaci[oó]n|partido|add-?on|activaci[oó]n)\b",
    re.IGNORECASE,
)
_OBSERVABLE_VERB = re.compile(
    r"\b(muestra|oculta|presenta|abre|cierra|visualiza|redirige|reproduce|"
    r"no (se )?muestra|no presenta|no abre|no visualiza|"
    r"ve |ven |retira|permanece|contin[uú]a|completa|ingresa|selecciona|"
    r"navega|disponible para el usuario|deja de (ver|visualizar)|ya no (ve|visualiza))\b",
    re.IGNORECASE,
)
_USER_SUBJECT = re.compile(r"^\s*(el )?usuario\b", re.IGNORECASE)
_IMPL_SUBJECT = re.compile(
    r"\b(el sistema|el backend|el servicio|el frontend|el fe\b|el handler|"
    r"la aplicaci[oó]n|el archivo|el asset|el recurso|el endpoint|"
    r"el hilo|el dispatcher|exoplayer|la cach[eé]|el cache|el manifesto|"
    r"module_version|query param)\b",
    re.IGNORECASE,
)
_IMPL_OPERATION = re.compile(
    r"\b(extrae(r)? (la )?url|persist(e|ir|ido)|coincid(e|ir) con (el )?archivo|"
    r"hilo de background|io dispatcher|isready|mapea(r)? (el )?campo|"
    r"bannerTitle|utiliza v\d+|module_version|"
    r"invoca|consulta (el|al|la) (servicio|endpoint|backend|api)|"
    r"realiza (la |una )?llamada|llama(da)? a (el )?endpoint|"
    r"espacio de color|srgb|interlaz|antialias|transparencia del (png|asset)|"
    r"peso objetivo|kilobytes?|\bkb\b|resoluci[oó]n (del|de) (asset|png|video)|"
    r"secuencia png|manifest_cdn|vp9|webm|codec|"
    r"sobrevive un reinicio|cache interna|archivo persistido)\b",
    re.IGNORECASE,
)
_ASSET_SPEC = re.compile(
    r"\b(srgb|interlaz|antialias|espacio de color|peso (objetivo|del archivo)|"
    r"transparencia|bordes del (png|asset)|resoluci[oó]n nativa|"
    r"formato del archivo|vp9|webm|secuencia de png)\b",
    re.IGNORECASE,
)
_CONDITION = re.compile(
    r"\b(feature flag|flag (habilit|deshabilit)|llave de (operaci|config)|"
    r"configuraci[oó]n (por regi[oó]n|regional|de operaci[oó]n|remota)|"
    r"obtenci[oó]n de configuraci[oó]n|intervalo de polling|"
    r"backend (debe|devuelve)|module_version\s*=|"
    r"habilitad[oa] en (la )?configuraci[oó]n)\b",
    re.IGNORECASE,
)
_SPECIAL_GIVEN = re.compile(
    r"\b(feature flag|flag|llave|configuraci[oó]n|module_version|"
    r"backend (devuelve|responde)|polling|regi[oó]n)\b",
    re.IGNORECASE,
)
_ACTIVATION_DOMAIN = re.compile(r"activaci[oó]n|consulta de estado", re.IGNORECASE)
_FLAG_SUPPRESS = re.compile(
    r"flag deshabilitado|impide toda consulta|no (realiza )?la consulta de (estado|activaci)",
    re.IGNORECASE,
)
_CONFIG_AS_SUBJECT = re.compile(
    r"obtenci[oó]n de configuraci[oó]n|intervalo de polling|"
    r"evaluaci[oó]n de la habilitaci[oó]n|seg[uú]n la llave|"
    r"^llave de configuraci[oó]n|creaci[oó]n de llaves|"
    r"gesti[oó]n din[aá]mica de configuraciones|"
    r"reflejo correcto de configuraciones",
    re.IGNORECASE,
)
_FLAG_ALLOW = re.compile(
    r"flag habilitado|permite la consulta de estado",
    re.IGNORECASE,
)
_NORMAL_GIVEN = re.compile(
    r"\b(usuario|cuenta (activa|v[aá]lida)|perfil|sesi[oó]n|loguead|"
    r"suscri(pto|pci[oó]n)|add-?on contratado)\b",
    re.IGNORECASE,
)


@dataclass
class ScenarioClassification:
    role: ScenarioRole
    given: list[str] = field(default_factory=list)
    when: list[str] = field(default_factory=list)
    then: list[str] = field(default_factory=list)
    observable_then: list[str] = field(default_factory=list)
    technical_notes: list[str] = field(default_factory=list)
    special_condition: str | None = None
    normal_precondition: str | None = None
    reason: str = ""


def split_gherkin_clauses(body: str) -> tuple[list[str], list[str], list[str]]:
    given: list[str] = []
    when: list[str] = []
    then: list[str] = []
    mode = "given"
    for raw in (body or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("|"):
            continue
        if re.match(r"^\s*Examples\s*:", line, re.I):
            break
        if _WHEN.match(line):
            mode = "when"
            when.append(_WHEN.sub("", line).strip())
        elif _THEN.match(line):
            mode = "then"
            then.append(_THEN.sub("", line).strip())
        elif _GIVEN.match(line):
            text = _GIVEN.sub("", line).strip()
            if mode == "when":
                when.append(text)
            elif mode == "then":
                then.append(text)
            else:
                given.append(text)
        elif _STEP.match(line):
            continue
        else:
            target = given if mode == "given" else when if mode == "when" else then
            if target:
                target[-1] = f"{target[-1]} {line}".strip()
    return given, when, then


def _has_observable_consequence(text: str) -> bool:
    if not text:
        return False
    mixed_ui = bool(
        (_USER_SUBJECT.search(text) or _USER_OR_UI.search(text)) and _OBSERVABLE_VERB.search(text)
    ) or bool(_NO_BLOCK_UX.search(text))
    if _ASSET_SPEC.search(text) or _IMPL_OPERATION.search(text):
        return mixed_ui
    if mixed_ui:
        return True
    if re.search(
        r"\bno (se )?muestra\b|\bse muestra\b|\bno visualiza\b|\bvisualiza\b|"
        r"\bse cierra\b|\bse abre\b|\bredirige\b|\bcompleta el pago\b|"
        r"\bactualiza(n)? el marcador\b|\bactualiza(n)? las alineaciones\b",
        text,
        re.I,
    ) and not _IMPL_SUBJECT.search(text):
        return True
    if _PRODUCT_UI.search(text) and _STATE_CHANGE.search(text) and not _ASSET_SPEC.search(text):
        return True
    return False


def _is_implementation_assertion(text: str) -> bool:
    if not text:
        return False
    if _ASSET_SPEC.search(text) and not _has_observable_consequence(text):
        return True
    if _IMPL_OPERATION.search(text) and not _has_observable_consequence(text):
        return True
    if _IMPL_SUBJECT.search(text) and not _has_observable_consequence(text):
        if re.search(
            r"\b(consulta|invoca|responde|extrae|persiste|utiliza|mapea|"
            r"descarga|coincide|ejecuta|llama)\b",
            text,
            re.I,
        ):
            return True
    return False


def _is_condition_assertion(text: str) -> bool:
    if not text:
        return False
    if _has_observable_consequence(text):
        return False
    return bool(_CONDITION.search(text))


def _observable_clauses(clauses: list[str]) -> list[str]:
    kept: list[str] = []
    for clause in clauses:
        parts = re.split(r"(?<=[.!?])\s+", clause)
        for part in parts:
            part = part.strip(" .;")
            if not part:
                continue
            if _has_observable_consequence(part):
                kept.append(part)
            elif " y " in part.lower() or " y el usuario" in part.lower():
                for piece in re.split(r"\s+y\s+", part, flags=re.I):
                    if _has_observable_consequence(piece):
                        kept.append(piece.strip())
    return kept


def _technical_clauses(clauses: list[str]) -> list[str]:
    notes: list[str] = []
    for clause in clauses:
        if _is_implementation_assertion(clause) or _IMPL_OPERATION.search(clause) or _ASSET_SPEC.search(clause):
            notes.append(clause)
        elif _IMPL_SUBJECT.search(clause) and not _has_observable_consequence(clause):
            notes.append(clause)
    return notes


def _preconditions(given: list[str], title: str, body: str) -> tuple[str | None, str | None]:
    normal: list[str] = []
    special: list[str] = []
    for clause in given:
        if _SPECIAL_GIVEN.search(clause):
            special.append(clause)
        elif _NORMAL_GIVEN.search(clause) or clause:
            normal.append(clause)
    if _CONDITION.search(title) or _CONDITION.search(body):
        if not special:
            special.append(title if _CONDITION.search(title) else "Condición técnica descrita en el Scenario.")
    return (
        "; ".join(dict.fromkeys(part for part in normal if part)) or None,
        "; ".join(dict.fromkeys(special)) or None,
    )


def classify_scenario(title: str, body: str) -> ScenarioClassification:
    given, when, then = split_gherkin_clauses(body)
    blob = f"{title}\n{body}"
    observable = _observable_clauses(then)
    if not observable and _has_observable_consequence(title):
        observable = [title.strip()]
    vis_placeholder = bool(re.search(r"<visibilidad>|<resultado>", blob, re.I))
    technical = _technical_clauses(then) + _technical_clauses(when)
    normal_pre, special_pre = _preconditions(given, title, body)
    impl_then = any(_is_implementation_assertion(clause) for clause in then) or (
        bool(then) and all(_is_implementation_assertion(clause) for clause in then)
    )
    cond_then = any(_is_condition_assertion(clause) for clause in then) or _is_condition_assertion(title)
    when_technical = any(_is_implementation_assertion(clause) or _IMPL_SUBJECT.search(clause) for clause in when)
    has_obs = bool(observable)
    if not has_obs and vis_placeholder:
        has_obs = True
    if (
        not has_obs
        and _USER_SUBJECT.search(title)
        and re.search(r"modal|activaci[oó]n|banner", title, re.I)
    ):
        has_obs = True

    if _OUT_OF_SCOPE.search(blob):
        return ScenarioClassification(
            role="F",
            given=given,
            when=when,
            then=then,
            technical_notes=technical,
            reason="Alcance explícitamente no entregado.",
        )
    if _QA_PROCESS.search(blob):
        return ScenarioClassification(
            role="E",
            given=given,
            when=when,
            then=then,
            technical_notes=technical,
            reason="Proceso QA/desarrollo/despliegue.",
        )
    if _METRICS.search(title) and not _NO_BLOCK_UX.search(blob):
        return ScenarioClassification(
            role="D",
            given=given,
            when=when,
            then=then,
            technical_notes=technical,
            reason="El Scenario valida telemetría o evento; no es QC de experiencia.",
        )
    if _METRICS.search(blob) and not _NO_BLOCK_UX.search(blob) and not has_obs:
        return ScenarioClassification(
            role="D",
            given=given,
            when=when,
            then=then,
            technical_notes=technical,
            reason="Métrica, analytics o telemetría sin consecuencia observable de QC.",
        )

    if _CONFIG_AS_SUBJECT.search(title) and not re.search(
        r"se muestra|no se muestra|visualiza|el usuario ve|no bloquea",
        blob,
        re.I,
    ):
        return ScenarioClassification(
            role="B",
            given=given,
            when=when,
            then=then,
            technical_notes=technical + then or [title],
            special_condition=special_pre or title,
            normal_precondition=normal_pre,
            reason="Condición o configuración necesaria para ejecutar un comportamiento.",
        )

    if not has_obs and _ACTIVATION_DOMAIN.search(blob) and _FLAG_SUPPRESS.search(blob):
        observable = [
            "El usuario no visualiza opciones de activación y continúa en la experiencia principal."
        ]
        has_obs = True
        special_pre = special_pre or title
    elif not has_obs and _ACTIVATION_DOMAIN.search(blob) and _FLAG_ALLOW.search(blob):
        observable = [
            "El usuario visualiza las opciones de activación cuando la funcionalidad está disponible."
        ]
        has_obs = True
        special_pre = special_pre or title

    if has_obs and (impl_then or when_technical or technical or _FLAG_SUPPRESS.search(blob) or _FLAG_ALLOW.search(blob)):
        return ScenarioClassification(
            role="G",
            given=given,
            when=when,
            then=then,
            observable_then=observable,
            technical_notes=technical,
            special_condition=special_pre,
            normal_precondition=normal_pre,
            reason="Cambio técnico con consecuencia funcional observable.",
        )
    if has_obs:
        return ScenarioClassification(
            role="A",
            given=given,
            when=when,
            then=then,
            observable_then=observable,
            technical_notes=technical,
            special_condition=special_pre,
            normal_precondition=normal_pre,
            reason="Comportamiento funcional observable.",
        )
    if cond_then or (_CONDITION.search(title) and not has_obs):
        return ScenarioClassification(
            role="B",
            given=given,
            when=when,
            then=then,
            technical_notes=technical + then,
            special_condition=special_pre or title,
            normal_precondition=normal_pre,
            reason="Condición o configuración necesaria para ejecutar un comportamiento.",
        )
    if impl_then or _ASSET_SPEC.search(blob) or _IMPL_OPERATION.search(blob) or (
        then and all(not _has_observable_consequence(clause) for clause in then)
    ):
        if _has_observable_consequence(title) or (_PRODUCT_UI.search(title) and _STATE_CHANGE.search(title)):
            return ScenarioClassification(
                role="G",
                given=given,
                when=when,
                then=then,
                observable_then=observable or [title.strip()],
                technical_notes=technical + then,
                special_condition=special_pre,
                normal_precondition=normal_pre,
                reason="El título declara consecuencia observable; el Then técnico queda en Datos de Prueba.",
            )
        return ScenarioClassification(
            role="C",
            given=given,
            when=when,
            then=then,
            technical_notes=technical or then or [title],
            special_condition=special_pre,
            normal_precondition=normal_pre,
            reason="Implementación técnica sin consecuencia observable de usuario.",
        )
    if special_pre and not has_obs:
        return ScenarioClassification(
            role="B",
            given=given,
            when=when,
            then=then,
            technical_notes=technical + then,
            special_condition=special_pre,
            normal_precondition=normal_pre,
            reason="Condición especial sin Then observable independiente.",
        )
    return ScenarioClassification(
        role="C",
        given=given,
        when=when,
        then=then,
        technical_notes=technical or [title],
        reason="Sin Then observable; no se inventa consecuencia funcional.",
    )


def record_classification(stats: GenerationStats, classification: ScenarioClassification, title: str) -> None:
    role = classification.role
    if role == "A":
        stats.materialized_a += 1
        stats.examples_a.append(title)
    elif role == "G":
        stats.materialized_g += 1
        stats.examples_g.append(title)
    elif role == "B":
        stats.converted_b += 1
        stats.examples_b.append(title)
    elif role == "C":
        stats.discarded_c += 1
        stats.examples_c.append(title)
    elif role == "D":
        stats.discarded_d += 1
        stats.examples_d.append(title)
    elif role == "E":
        stats.discarded_e += 1
        stats.examples_e.append(title)
    elif role == "F":
        stats.discarded_f += 1
        stats.examples_f.append(title)
