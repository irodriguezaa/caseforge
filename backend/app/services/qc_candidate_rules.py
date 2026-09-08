"""Deterministic QC rules applied after Jira/Gherkin or LLM proposals.

AI may propose; these rules filter technical/metrics/QA-process noise, group equivalent
user-observable flows, assign Blocker/Critical, and calibrate confidence.
"""

from __future__ import annotations

import re
from typing import Literal

from app.schemas.case_generation import CandidateStep, GeneratedCaseCandidate, GenerationStats

Priority = Literal["BLOCKER", "CRITICAL"]
Confidence = Literal["high", "medium", "low"]

_METRICS_ONLY = re.compile(
    r"\b(m[eé]tric|analytics|anal[ií]tica|ga4|firebase|\bdat\b|tracking|"
    r"pipeline|schema|esquema de m[eé]tricas|instrument|"
    r"payment_method_selected|checkout_start|checkout_success|checkout_error|"
    r"nomenclatura DAT|evento de (selecci[oó]n|anal|inicio de checkout|error de pago|xito de pago))\b",
    re.IGNORECASE,
)
_USER_OBSERVABLE = re.compile(
    r"\b(ve|visualiza|muestra|oculta|abre|cierra|ingresa|selecciona|reproduce|"
    r"contin[uú]a|permanece|no bloquea|no se muestra|redirige|completa|"
    r"usuario|modal|banner|[ií]tem|pesta[nñ]a|error)\b",
    re.IGNORECASE,
)
_QA_PROCESS = re.compile(
    r"desviaci[oó]n de nomenclatura|correcci[oó]n de desviaci[oó]n|"
    r"habilita el despliegue|reporta antes del despliegue|proceso de QA",
    re.IGNORECASE,
)
_EVENT_TITLE = re.compile(
    r"se registra evento|evento de (selecci|anal[ií]tica|inicio|[eé]xito|error|clic)|"
    r"transmisi[oó]n y persistencia del evento|la estructura del evento|"
    r"carga el esquema de m[eé]tricas|esquema de m[eé]tricas por defecto|"
    r"nomenclatura DAT|dispara el evento|se instrumenta|payment_method_selected|"
    r"incluye trazabilidad",
    re.IGNORECASE,
)
_INTERNAL_ONLY = re.compile(
    r"registro en logs|registro del tiempo transcurrido|invoca finish|"
    r"estructura del evento|cumple el esquema|handler lee|"
    r"no notifica al backend",
    re.IGNORECASE,
)
_BLOCKER = re.compile(
    r"\b(acceso|login|activar|activaci[oó]n|cuenta|suscrip|"
    r"reproduc|playback|player|bookmark|contin[uú]a viendo|fin de player|"
    r"canal lineal|linear|"
    r"transacci|paypal|pago|checkout|compra|"
    r"parental|cancelaci|"
    r"npvr|timeshift|time[\s-]?shift|perfiles?)\b",
    re.IGNORECASE,
)
_TECHNICAL_ACTION = re.compile(
    r"\b(invoca|dispara la consulta|solicita GET|solicita POST|"
    r"el sistema consulta|el backend|el servicio responde|"
    r"lee el code|query param|feature flag|module_version)\b",
    re.IGNORECASE,
)
_PAREN_VARIANTS = re.compile(r"\([^)]*\)")

FUNCTIONAL_EXAMPLE_KEYS = re.compile(
    r"^(plan|add-?on|paquete|producto|contenido|proveedor|provider)$",
    re.IGNORECASE,
)
OUTCOME_EXAMPLE_KEYS = re.compile(
    r"^(visibilidad|resultado|expected|outcome)$",
    re.IGNORECASE,
)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def is_metrics_or_qa_process(title: str, body: str) -> bool:
    blob = f"{title}\n{body}"
    if _QA_PROCESS.search(blob):
        return True
    if _INTERNAL_ONLY.search(title) and not re.search(r"no bloquea", blob, re.IGNORECASE):
        return True
    if _EVENT_TITLE.search(title) and not re.search(r"no bloquea", blob, re.IGNORECASE):
        return True
    if _METRICS_ONLY.search(blob) and not (
        _USER_OBSERVABLE.search(blob) or re.search(r"no bloquea", blob, re.I)
    ):
        return True
    if _METRICS_ONLY.search(title) and not (
        _USER_OBSERVABLE.search(blob) or re.search(r"no bloquea", blob, re.I)
    ):
        return True
    return False


def is_metrics_only_candidate(candidate: GeneratedCaseCandidate) -> bool:
    blob = f"{candidate.name} {candidate.justification} {candidate.evidence}"
    steps = " ".join(f"{step.action} {step.expected_result}" for step in candidate.steps)
    return is_metrics_or_qa_process(candidate.name, f"{steps} {blob}")


def classify_priority(name: str, steps: list[CandidateStep], extra: str | None = None) -> Priority:
    blob = " ".join(
        [name, extra or ""]
        + [f"{step.action} {step.expected_result}" for step in steps]
    )
    if _BLOCKER.search(blob):
        return "BLOCKER"
    return "CRITICAL"


def classify_confidence(
    *,
    requires_condition: bool,
    basic_validation: bool,
    steps: list[CandidateStep],
    technical_heavy: bool,
) -> Confidence:
    if basic_validation:
        return "low"
    step_blob = " ".join(f"{step.action} {step.expected_result}" for step in steps)
    still_technical = bool(_TECHNICAL_ACTION.search(step_blob))
    if requires_condition or technical_heavy or still_technical:
        return "medium"
    return "high"


def functional_title(title: str, expected: list[str]) -> str:
    core = title.strip()
    if _TECHNICAL_ACTION.search(_PAREN_VARIANTS.sub("", core)) or re.search(
        r"/[A-Za-z]|GET |POST |status=", _PAREN_VARIANTS.sub("", core)
    ):
        if expected:
            suffix = ""
            parens = re.findall(r"\(([^)]*)\)", title)
            keep = [
                part
                for part in parens
                if not re.search(
                    r"origen=|origin=|code=|status=|accion=|show_modal=",
                    part,
                    re.IGNORECASE,
                )
            ]
            if keep:
                suffix = " (" + "; ".join(keep) + ")"
            return (expected[0] + suffix)[:250]
    return core[:250] or title[:250]


def variant_token(name: str, test_data: str | None) -> str:
    """Keep functional/outcome variants in the fingerprint; ignore technical labels."""
    tokens: list[str] = []
    for part in re.findall(r"\(([^)]*)\)", name):
        if re.search(
            r"origen=|origin=|code=|status=|accion=|show_modal=|operaci|label=|breakpoint=",
            part,
            re.IGNORECASE,
        ):
            continue
        tokens.append(part.strip())
    if test_data:
        tokens.extend(
            f"{key}={value.strip()}"
            for key, value in re.findall(
                r"\b(plan|add-?on|paquete|producto)=([^,;]+)",
                test_data,
                re.IGNORECASE,
            )
        )
    return normalize(" | ".join(tokens))


def ux_fingerprint(name: str, steps: list[CandidateStep], test_data: str | None = None) -> str:
    actions = " ".join(step.action for step in steps)
    expected = " ".join(step.expected_result for step in steps)
    return normalize(f"{actions}|{expected}|{variant_token(name, test_data)}")


def example_strategy(examples: list[dict[str, str]]) -> str:
    """group | split_functional | group_by_outcome."""
    if not examples:
        return "group"
    keys = list(examples[0].keys())
    if any(OUTCOME_EXAMPLE_KEYS.match(key or "") for key in keys):
        return "group_by_outcome"
    if any(FUNCTIONAL_EXAMPLE_KEYS.match(key or "") for key in keys):
        return "split_functional"
    return "group"


def group_examples_by_outcome(
    examples: list[dict[str, str]],
) -> dict[str, list[dict[str, str]]]:
    buckets: dict[str, list[dict[str, str]]] = {}
    outcome_key = next(
        (key for key in examples[0].keys() if OUTCOME_EXAMPLE_KEYS.match(key or "")),
        None,
    )
    if not outcome_key:
        return {"all": examples}
    for example in examples:
        label = (example.get(outcome_key) or "").strip() or "same"
        buckets.setdefault(label, []).append(example)
    return buckets


def format_examples(examples: list[dict[str, str]]) -> str:
    lines = []
    for example in examples:
        label = ", ".join(f"{key}={value}" for key, value in example.items() if value)
        if label:
            lines.append(label)
    return "Variantes técnicas (mismo comportamiento de usuario): " + "; ".join(lines)


def extract_user_type(text: str) -> str | None:
    match = re.search(
        r"\b(Administrador|Admin|Miembro|Kids?|Infantil|Invitado)\b",
        text,
        re.IGNORECASE,
    )
    return match.group(1) if match else None


_STEP_PREFIX = re.compile(r"^\s*\d+\.\s*")
_INTERNAL_SUBJECT = re.compile(
    r"\b(el sistema|el backend|la web app|el servicio|el frontend|el fe\b|el handler|la aplicaci[oó]n)\b",
    re.IGNORECASE,
)
_INTERNAL_VERB = re.compile(
    r"\b(consulta|consulto|invoca|ejecuta|obtiene|valida|dispara|env[ií]a|lee|relee|"
    r"registra|reintenta|mantiene el code|no (realiza )?la consulta|responde|"
    r"notifica al backend|descarta|inicia el flujo|reserva)\b",
    re.IGNORECASE,
)
_USER_SUBJECT = re.compile(r"^\s*(el )?usuario\b", re.IGNORECASE)
_OBSERVABLE_VERB = re.compile(
    r"\b(muestra|oculta|presenta|abre|cierra|visualiza|redirige|no muestra|"
    r"no presenta|no abre|ve |ven |retira)\b",
    re.IGNORECASE,
)
_A11Y_AUDIT = re.compile(r"\bWCAG\b|accesibilidad|ARIA|roles y etiquetas", re.IGNORECASE)
_PLACEHOLDER_EXPECTED = re.compile(
    r"observa el resultado en la interfaz|"
    r"se observa el resultado declarado en el escenario|"
    r"se observa el comportamiento de usuario final declarado en el escenario",
    re.IGNORECASE,
)
_UI_OBJECT = re.compile(
    r"\b(banner|modal|qr|[ií]tem|player|mini ?player|tarjeta|home|pago|paypal|"
    r"checkout|carrusel|live ?feed|marcador)\b",
    re.IGNORECASE,
)
_NEG_POLARITY = re.compile(
    r"\bno (se )?(muestra|visualiza|presenta|abre|ve)|oculta|cierra|"
    r"deja de (ver|visualizar)|ya no (ve|visualiza)|retira",
    re.IGNORECASE,
)
_POS_POLARITY = re.compile(
    r"\b(se muestra|visualiza|presenta|abre|ve el|ve la|muestra el|muestra la)\b",
    re.IGNORECASE,
)


def _bare(text: str) -> str:
    return _STEP_PREFIX.sub("", (text or "").strip())


def is_internal_claim(text: str) -> bool:
    """Semantic: internal subject+verb or implementation detail, not 'el usuario consulta…'."""
    bare = _bare(text)
    if not bare:
        return False
    if _USER_SUBJECT.match(bare):
        return False
    if re.search(r"/oauth|/activate\b|idempotencia|query param|token Bearer", bare, re.I):
        return True
    if re.search(
        r"utiliza v\d+|module_version|extrae(r)? (la )?url|archivo persistido|"
        r"espacio de color|srgb|isready|hilo de background|bannerTitle",
        bare,
        re.I,
    ) and not _OBSERVABLE_VERB.search(bare):
        return True
    if re.search(r"se obtiene la configuraci|el backend responde", bare, re.I):
        return True
    if re.search(r"log de observabilidad|registra el fallo de env[ií]o", bare, re.I):
        return True
    has_internal_subject = bool(_INTERNAL_SUBJECT.search(bare))
    has_internal_verb = bool(_INTERNAL_VERB.search(bare))
    has_observable = bool(_OBSERVABLE_VERB.search(bare))
    if has_internal_subject and has_internal_verb:
        return True
    if has_internal_subject and has_observable and not has_internal_verb:
        return False
    return False


def _to_user_visible_system_show(text: str) -> str:
    bare = _bare(text)
    updated = re.sub(r"\bel sistema\b", "el usuario", bare, flags=re.IGNORECASE)
    updated = re.sub(r"\bno muestra\b", "no visualiza", updated, flags=re.IGNORECASE)
    updated = re.sub(r"\bmuestra\b", "visualiza", updated, flags=re.IGNORECASE)
    updated = re.sub(r"\bpresenta\b", "ve", updated, flags=re.IGNORECASE)
    if updated:
        updated = updated[0].upper() + updated[1:]
    return updated


def rewrite_internal_to_observable(text: str, name: str) -> tuple[str, str | None]:
    """Translate an internal claim into user-observable wording. Returns (text, tech_for_test_data).

    Does not invent a generic observable result when Jira does not provide one.
    """
    bare = _bare(text)
    if not bare:
        return text, None
    blob_early = f"{bare} {name}".lower()
    if re.search(r"no bloquea|no se bloquea", blob_early) and re.search(
        r"anal[ií]tica|evento|dat\b|m[eé]tric", blob_early
    ):
        return "El usuario puede completar el pago; la experiencia no se bloquea.", bare
    user_span = re.search(r"(el usuario\b.+)$", bare, re.IGNORECASE | re.DOTALL)
    if user_span and _OBSERVABLE_VERB.search(user_span.group(1)):
        visible = user_span.group(1).strip()
        visible = visible[0].upper() + visible[1:]
        tech = bare[: user_span.start()].strip(" y,;.") or None
        return visible, tech
    if not is_internal_claim(bare):
        if _INTERNAL_SUBJECT.search(bare) and _OBSERVABLE_VERB.search(bare):
            return _to_user_visible_system_show(bare), None
        return bare, None

    extra = bare
    blob = f"{bare} {name}".lower()

    if re.search(r"retira del carrusel|retira el [ií]tem", blob):
        return "El usuario ya no ve el ítem de activación en el carrusel.", extra
    if re.search(r"reserva espacio|sin imagen configurada", blob):
        return "El modal se muestra sin un espacio vacío de imagen.", extra
    if re.search(r"no bloquea|no se bloquea", blob) and re.search(
        r"anal[ií]tica|evento|log|dat\b", blob
    ):
        return "El usuario puede completar el pago; la experiencia no se bloquea.", extra
    if re.search(r"no (realiza )?la consulta|no consulta|inhibe la consulta|no activa la funcionalidad", blob):
        return (
            "El usuario no visualiza opciones de activación y continúa en la experiencia principal.",
            extra,
        )
    if re.search(r"show_activation_modal|activation_permanently_suppressed|backend responde con status", blob):
        if re.search(r"suppress|no presenta|vinculad", blob):
            return "El usuario no vuelve a ver el Modal de activación y continúa en la experiencia principal.", extra
        return "El usuario ve el Modal o las opciones de activación de acuerdo con el estado de su cuenta.", extra
    if re.search(r"se obtiene la configuraci", blob):
        return "El usuario ve la experiencia y los textos por defecto de su región.", extra
    if re.search(r"notifica al backend la supresi", blob):
        return "El Modal no vuelve a mostrarse y el usuario permanece en la pantalla activa.", extra
    if re.search(r"descarta cualquier url|no redirige", blob):
        return "El usuario no es redirigido a HBO Max y permanece en Claro video.", extra
    if re.search(r"inicia el flujo de activaci[oó]n sin presentar el modal", blob):
        return "El usuario entra al flujo de activación sin ver el Modal inicial.", extra
    if re.search(r"re-consulta|consulta nuevamente|/oauth.*re-?ingres|recupera el foco", blob):
        return (
            "Al volver a la experiencia, el usuario ve las opciones de activación actualizadas según su cuenta.",
            extra,
        )
    if re.search(r"reintent", blob) and re.search(r"/oauth|activaci", blob):
        return (
            "El usuario permanece en el flujo de activación y ve en pantalla el resultado (éxito o error).",
            extra,
        )
    if re.search(r"/oauth|idempotencia|ejecuta el servicio|/activate|redirect_url", blob):
        return "Se abre la experiencia de activación y el usuario puede continuar el proceso.", extra
    if re.search(r"query param|relee el code|mantiene el code", blob):
        return (
            "El usuario permanece en el flujo de activación y puede continuar o reingresar el código en pantalla.",
            extra,
        )
    if re.search(r"consulta de estado|consulta la consulta", blob):
        return (
            "Las opciones de activación se muestran al usuario de acuerdo con las condiciones de su cuenta.",
            extra,
        )
    if re.search(r"no (realiza )?ninguna llamada|no llama(da)? a (el )?endpoint", blob):
        return extra, extra
    return extra, extra


def rewrite_case_name(name: str, expected: list[str]) -> str:
    bare = (name or "").strip()
    if re.search(r"flag deshabilitado|impide toda consulta", bare, re.I):
        return "El usuario no visualiza opciones de activación cuando la funcionalidad no está disponible."
    if re.search(r"flag habilitado|permite la consulta de estado", bare, re.I):
        return "El usuario visualiza las opciones de activación cuando la funcionalidad está disponible."
    if is_internal_claim(bare) or re.match(r"el sistema (consulta|consulto|obtiene|ejecuta)", bare, re.I):
        if expected:
            return expected[0][:250]
    if _INTERNAL_SUBJECT.match(bare) and _OBSERVABLE_VERB.search(bare) and not is_internal_claim(bare):
        return _to_user_visible_system_show(bare)[:250]
    return functional_title(bare, expected)


def rewrite_step_language(step: CandidateStep, name: str = "") -> CandidateStep:
    action_bare = _bare(step.action)
    extra_parts: list[str] = []
    if step.test_data:
        extra_parts.append(step.test_data)

    if is_internal_claim(action_bare) or re.search(
        r"env[ií]o del evento|timeout de red|dispara payment_", action_bare, re.I
    ):
        extra_parts.append(action_bare)
        if re.search(r"pago|paypal|no bloquea", name, re.I):
            action = "El usuario completa el flujo de pago."
        else:
            action = "El usuario ingresa al flujo correspondiente en la experiencia."
    elif _TECHNICAL_ACTION.search(action_bare) or re.search(r"\b(GET|POST|HTTP|/services/)\b", action_bare, re.I):
        tech = action_bare
        extra_parts.append(tech)
        action = "El usuario ingresa al flujo correspondiente en la experiencia."
    else:
        action = action_bare

    expected, expected_tech = rewrite_internal_to_observable(step.expected_result, name)
    if expected_tech:
        extra_parts.append(expected_tech)

    test_data = "; ".join(dict.fromkeys(part for part in extra_parts if part)) or None
    return CandidateStep(
        step_number=step.step_number,
        action=action,
        expected_result=expected,
        test_data=test_data,
    )


def is_accessibility_audit_only(candidate: GeneratedCaseCandidate, release_context: dict | None) -> bool:
    blob = " ".join(
        [candidate.name]
        + [f"{step.action} {step.expected_result}" for step in candidate.steps]
    )
    if not _A11Y_AUDIT.search(blob):
        return False
    hints = []
    if release_context:
        hints.append(str(release_context.get("description") or ""))
        analysis = release_context.get("analysis") or {}
        for item in analysis.get("observations") or []:
            hints.append(str(item))
    hinted = bool(re.search(r"wcag|accesib", " ".join(hints), re.I))
    # Pure ARIA/WCAG checklist is not observable by ClaroVideo end-user QC.
    aria_only = bool(re.search(r"\bARIA\b|roles y etiquetas|WCAG 2", blob, re.I))
    return hinted or aria_only


def is_placeholder_expected(text: str) -> bool:
    return bool(_PLACEHOLDER_EXPECTED.search(text or ""))


def _polarity(text: str) -> str:
    if _NEG_POLARITY.search(text or ""):
        return "neg"
    if _POS_POLARITY.search(text or ""):
        return "pos"
    return "neu"


def _ui_objects(text: str) -> set[str]:
    return {match.group(0).lower() for match in _UI_OBJECT.finditer(text or "")}


def align_title_with_flow(name: str, steps: list[CandidateStep]) -> str:
    """Title must describe the same flow as the last observable expected result."""
    if not steps:
        return name
    expected = steps[-1].expected_result or ""
    shared = _ui_objects(name) & _ui_objects(expected)
    if (
        shared
        and _polarity(name) != "neu"
        and _polarity(expected) != "neu"
        and _polarity(name) != _polarity(expected)
    ):
        return expected[:250]
    return name


def _ux_normalize(text: str) -> str:
    cleaned = _PAREN_VARIANTS.sub(" ", text or "")
    cleaned = re.sub(
        r"\b(origen|origin|code|status|flag|http|module_version)[^\s,;]*",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = normalize(cleaned)
    cleaned = re.sub(r"\bvisualiza\b", "ve", cleaned)
    cleaned = re.sub(r"\bpresenta\b", "ve", cleaned)
    cleaned = re.sub(r"\bno se muestra\b", "no ve", cleaned)
    cleaned = re.sub(r"\bno muestra\b", "no ve", cleaned)
    return cleaned


def observable_fingerprint(
    steps: list[CandidateStep], name: str = "", test_data: str | None = None
) -> str:
    """Same observable PASS/FAIL, ignoring Story/HTTP/flag/origin labels.

    Functional variants (plan, add-on, visibilidad) stay in the fingerprint.
    """
    expected = " ".join(step.expected_result for step in steps)
    return normalize(f"{_ux_normalize(expected)}|{variant_token(name, test_data)}")


def candidate_lacks_observable_qc(candidate: GeneratedCaseCandidate) -> bool:
    if not candidate.steps:
        return True
    return all(
        is_internal_claim(step.expected_result) or is_placeholder_expected(step.expected_result)
        for step in candidate.steps
    )


def merge_candidates(group: list[GeneratedCaseCandidate]) -> GeneratedCaseCandidate:
    primary = group[0]
    extra_data = []
    extra_evidence = []
    extra_jira = []
    extra_epic = []
    extra_pre = []
    extra_covers: list[str] = []
    extra_rules: list[str] = []
    for item in group:
        if item.test_data:
            extra_data.append(item.test_data)
        extra_evidence.append(item.evidence.split("\n", 1)[0] if item.evidence else "")
        if item.related_jira:
            extra_jira.extend(part.strip() for part in item.related_jira.split("|") if part.strip())
        if item.related_functionality:
            extra_epic.extend(
                part.strip() for part in item.related_functionality.split("|") if part.strip()
            )
        if item.precondition:
            extra_pre.append(item.precondition)
        extra_covers.extend(item.covers or [])
        extra_rules.extend(item.applied_rules or [])
    jiras = list(dict.fromkeys(extra_jira))
    epics = list(dict.fromkeys(extra_epic))
    steps = [rewrite_step_language(step, primary.name) for step in primary.steps]
    test_data = "; ".join(dict.fromkeys(extra_data)) or primary.test_data
    technical_heavy = bool(test_data and len(test_data) > 80)
    expected = [step.expected_result for step in steps]
    name = align_title_with_flow(rewrite_case_name(primary.name, expected), steps)
    user_type = primary.user_type or extract_user_type(
        f"{primary.precondition or ''} {test_data or ''} {primary.name}"
    )
    consolidated = len(group) > 1
    justification = primary.justification
    if consolidated:
        justification += (
            " Consolidado: mismo comportamiento observable; se conservan todas las "
            "referencias Jira/Scenario en la evidencia."
        )
    return GeneratedCaseCandidate(
        name=name,
        description=primary.description,
        precondition="; ".join(dict.fromkeys(extra_pre)) or primary.precondition,
        requires_condition=any(item.requires_condition for item in group),
        steps=steps,
        test_data=test_data,
        related_functionality=" | ".join(epics) if epics else primary.related_functionality,
        related_jira=" | ".join(jiras) if jiras else primary.related_jira,
        related_rn=primary.related_rn,
        evidence=" | ".join(dict.fromkeys(part for part in extra_evidence if part))[:2000],
        justification=justification,
        possible_duplicate_of=primary.possible_duplicate_of,
        confidence=classify_confidence(
            requires_condition=any(item.requires_condition for item in group),
            basic_validation=primary.basic_validation,
            steps=steps,
            technical_heavy=technical_heavy,
        ),
        review_required=True,
        basic_validation=primary.basic_validation,
        priority=classify_priority(name, steps, test_data),
        user_type=user_type,
        covers=list(dict.fromkeys(extra_covers)),
        applied_rules=list(dict.fromkeys(extra_rules)),
        generation_origin=primary.generation_origin,
        origin_release_id=primary.origin_release_id,
        origin_release_name=primary.origin_release_name,
        related_origin_case_ids=list(primary.related_origin_case_ids or []),
    )


def _bucket_merge(
    items: list[tuple[str, GeneratedCaseCandidate]],
    stats: GenerationStats | None,
    count_consolidation: bool,
) -> list[GeneratedCaseCandidate]:
    buckets: dict[str, list[GeneratedCaseCandidate]] = {}
    order: list[str] = []
    for key, candidate in items:
        if key not in buckets:
            order.append(key)
        buckets.setdefault(key, []).append(candidate)
    merged: list[GeneratedCaseCandidate] = []
    for key in order:
        group = buckets[key]
        if count_consolidation and len(group) > 1 and stats is not None:
            stats.consolidated_functional += len(group) - 1
            stats.examples_consolidated.append(
                " + ".join(item.name for item in group)[:240]
            )
        merged.append(merge_candidates(group))
    return merged


def apply_qc_rules(
    candidates: list[GeneratedCaseCandidate],
    release_context: dict | None = None,
    stats: GenerationStats | None = None,
) -> list[GeneratedCaseCandidate]:
    kept: list[tuple[str, GeneratedCaseCandidate]] = []
    for candidate in candidates:
        if is_metrics_only_candidate(candidate):
            continue
        if is_accessibility_audit_only(candidate, release_context):
            continue
        original_name = candidate.name
        rewritten_steps = [rewrite_step_language(step, original_name) for step in candidate.steps]
        extra_from_steps = [step.test_data for step in rewritten_steps if step.test_data]
        if extra_from_steps:
            candidate.test_data = "; ".join(
                dict.fromkeys(part for part in [candidate.test_data, *extra_from_steps] if part)
            )
        candidate.steps = rewritten_steps
        candidate.name = align_title_with_flow(
            rewrite_case_name(original_name, [step.expected_result for step in rewritten_steps]),
            rewritten_steps,
        )
        if candidate_lacks_observable_qc(candidate):
            continue
        if candidate.covers:
            cluster_key = (
                "covers:"
                + "|".join(sorted(candidate.covers))
                + "|"
                + ux_fingerprint(original_name, rewritten_steps, candidate.test_data)
            )
        else:
            cluster_key = (
                f"{candidate.related_jira or candidate.related_functionality or ''}|"
                f"{ux_fingerprint(original_name, rewritten_steps, candidate.test_data)}"
            )
        if candidate.user_type is None:
            candidate.user_type = extract_user_type(
                f"{candidate.precondition or ''} {candidate.test_data or ''} {candidate.name}"
            )
        candidate.priority = candidate.priority or classify_priority(
            candidate.name, rewritten_steps, candidate.test_data
        )
        still_interpreted = is_internal_claim(original_name) or candidate.requires_condition
        candidate.confidence = classify_confidence(
            requires_condition=candidate.requires_condition,
            basic_validation=candidate.basic_validation,
            steps=rewritten_steps,
            technical_heavy=bool(candidate.test_data and len(candidate.test_data) > 80)
            or still_interpreted,
        )
        kept.append((cluster_key, candidate))

    story_merged = _bucket_merge(kept, stats, count_consolidation=False)
    cross_story: list[tuple[str, GeneratedCaseCandidate]] = []
    for index, item in enumerate(story_merged):
        if item.basic_validation:
            key = f"basic:{item.related_jira or index}"
        else:
            key = (
                observable_fingerprint(item.steps, item.name, item.test_data)
                or f"unique:{index}"
            )
        cross_story.append((key, item))
    return _bucket_merge(cross_story, stats, count_consolidation=True)
