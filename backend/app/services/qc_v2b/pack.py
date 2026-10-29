"""Consolidación post-generación: paquete QC ejecutable, no inventario exhaustivo."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import replace

from app.services.qc_candidate_rules import is_key_config_scenario
from app.services.qc_v2.collect import EpicBundle
from app.services.qc_v2.stages import DesignedCase, Scenario, complexity, validate_case
from app.services.qc_v2b.eligibility import ESTADO_HPA, ESTADO_QA, ESTADO_REGRESSION, ESTADO_TECH

_USER_PATTERNS = [
    (re.compile(r"telmex fuera de casa", re.I), "Usuario Telmex fuera de casa"),
    (re.compile(r"\bip telmex\b", re.I), "Usuario IP Telmex"),
    (re.compile(r"usuario externo|externo", re.I), "Usuario externo"),
    (re.compile(r"clarovideo|claro video", re.I), "Usuario Claro video"),
    (re.compile(r"suscri", re.I), "Usuario suscrito"),
    (re.compile(r"invitad", re.I), "Usuario invitado"),
]
_ENTRY_NOISE = re.compile(
    r"por primera vez|acaba de registr|reci[eé]n adquir|ya (lo )?tiene|"
    r"inicia sesi[oó]n|se registra|tras recargar|sale y vuelve",
    re.IGNORECASE,
)
_STATE = re.compile(r"despleg\w*|repleg\w*|ocult\w*|no se muestra|mensaje de error", re.IGNORECASE)
_HPA_TYPE_OR_NAV = re.compile(
    r"\b(atr[aá]s|cancelar|reintento|recargar|persistencia|salir y volver)\b",
    re.IGNORECASE,
)
_REGRESSION_STEP = re.compile(
    r"recargar|salir .{0,40}volver|ir a otra secci[oó]n y volver",
    re.IGNORECASE,
)
_OPTIONAL_VARIANT = re.compile(
    r"compra real|adquir(ir|ido)|enable\s*=\s*false|configuraci[oó]n especial",
    re.IGNORECASE,
)
_OTHER_OP = re.compile(
    r"colombia|per[uú]|argentina|brasil|chile|centroam[eé]rica|"
    r"operaci[oó]n distinta|otra operaci[oó]n",
    re.IGNORECASE,
)
_PAY = re.compile(r"paypal|tarjeta|m[eé]todo de pago|\bmdp\b|checkout|pago", re.IGNORECASE)
_DUP_WORDS = re.compile(r"\b(\w+)(\s+\1\b)+", re.IGNORECASE)
_BROKEN_END = re.compile(r"[\s,;:/]+$")


def _norm(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text or "")
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", folded).strip().lower()


def _blob(case: DesignedCase, include_variants: bool = True) -> str:
    parts = [case.titulo, " ".join(case.precondiciones)]
    parts += [f"{s['accion']} {s['resultado_esperado']}" for s in case.pasos]
    if include_variants:
        parts += [f"{v['condicion']} {v['resultado_esperado']}" for v in case.variantes]
    return " ".join(parts)


def user_label(case: DesignedCase) -> str:
    text = _blob(case)
    for pattern, label in _USER_PATTERNS:
        if pattern.search(text):
            return label
    return "Usuario"


def visible_state(case: DesignedCase) -> str:
    text = _blob(case)
    if re.search(r"despleg", text, re.I):
        return "el componente desplegado"
    if re.search(r"repleg", text, re.I):
        return "el componente replegado"
    if re.search(r"ocult", text, re.I):
        return "el componente oculto"
    if re.search(r"no se muestra", text, re.I):
        return "que no se muestra"
    if re.search(r"mensaje de error", text, re.I):
        return "el mensaje de error en pantalla"
    if case.tipo == "ERG":
        return "conformidad con el diseño"
    return ""


def story_asks_operations(bundle: EpicBundle) -> bool:
    text = " ".join(
        [bundle.summary]
        + [story.summary + story.context for story in bundle.technical_stories]
        + [story.summary for story in bundle.user_stories]
    )
    return bool(re.search(r"operaciones|por operaci[oó]n|cada operaci[oó]n", text, re.I))


def story_is_payments(bundle: EpicBundle) -> bool:
    text = " ".join([bundle.summary] + [s.summary for s in bundle.technical_stories + bundle.user_stories])
    return bool(re.search(r"\bpago|checkout|m[eé]todo de pago|pasarela\b", text, re.I))


def _trim_title(title: str) -> str:
    clean = _DUP_WORDS.sub(r"\1", title)
    clean = re.sub(r"\s{2,}", " ", clean).strip()
    clean = _BROKEN_END.sub("", clean)
    if len(clean) > 140:
        clean = clean[:137].rsplit(" ", 1)[0] + "…"
    return clean


def rewrite_title(case: DesignedCase) -> str:
    original = _trim_title(case.titulo)
    duplicated = len(re.findall(r"\busuario\b", original, re.I)) >= 2
    already_ok = (
        original.lower().startswith("usuario")
        and 4 <= len(original.split()) <= 16
        and not duplicated
        and "…" not in original
    )
    if already_ok and case.tipo != "ERG":
        return original
    user = user_label(case)
    blob = _norm(case.titulo + " " + " ".join(s["accion"] for s in case.pasos[:1]))
    if case.tipo == "ERG":
        title = f"{user} compara el componente con el diseño"
    elif "registr" in blob:
        title = f"{user} registra y ve {visible_state(case) or 'el resultado en pantalla'}"
    elif "inicia sesion" in blob or "login" in blob:
        title = f"{user} inicia sesión y ve {visible_state(case) or 'el resultado en pantalla'}"
    elif "ocult" in blob or "no se muestra" in blob:
        title = f"{user} no ve el componente"
    else:
        title = f"{user} ve {visible_state(case) or 'el resultado en pantalla'}"
    return _trim_title(title[0].upper() + title[1:] if title else original)


def assign_priority(case: DesignedCase) -> tuple[str, str | None]:
    """Persisted band (BLOCKER/CRITICAL) plus optional display Major."""
    if case.tipo == "ERG":
        return "CRITICAL", "MAJOR"
    text = _blob(case)
    if case.tipo == "HPP" and re.search(r"despleg|flujo principal", text, re.I) and not re.search(
        r"repleg|ocult|no se muestra", text, re.I
    ):
        return "BLOCKER", None
    return "CRITICAL", None


def _cap_variants(case: DesignedCase, bundle: EpicBundle) -> DesignedCase:
    variants = []
    allow_ops = story_asks_operations(bundle)
    allow_pay = story_is_payments(bundle)
    for variant in case.variantes:
        condition = variant["condicion"]
        if not allow_ops and _OTHER_OP.search(condition):
            continue
        if not allow_pay and _PAY.search(condition) and not _PAY.search(case.titulo):
            continue
        if _OPTIONAL_VARIANT.search(condition) and not condition.lower().startswith("opcional"):
            condition = f"opcional: {condition}"
        variants.append({**variant, "condicion": condition})
    return replace(case, variantes=variants[:3])


def _trim_regression_steps(case: DesignedCase) -> DesignedCase:
    kept = [step for step in case.pasos if not _REGRESSION_STEP.search(step["accion"])]
    if len(kept) < 3:
        return case
    if len(kept) > 6:
        kept = kept[:6]
    return replace(case, pasos=kept)


def _relabel(case: DesignedCase) -> DesignedCase:
    text = _blob(case)
    tipo = case.tipo
    if (
        tipo == "TTF"
        and re.search(r"repleg|ocult|no se muestra", text, re.I)
        and not re.search(r"error|fallo|no debe", text, re.I)
        and not _OTHER_OP.search(text)
    ):
        tipo = "HPP"
    return replace(case, tipo=tipo, titulo=rewrite_title(replace(case, tipo=tipo)))


def _discard_reason(case: DesignedCase) -> tuple[str, str] | None:
    text = _blob(case, include_variants=False)
    if case.tipo == "HPA" or (_HPA_TYPE_OR_NAV.search(case.titulo) and case.tipo != "HPP"):
        return ESTADO_HPA, "HPA (Atrás, cancelar, reintento, recargar, persistencia) queda fuera del paquete QC"
    if case.tipo == "E2E" and re.search(r"no se rompe|conservaci[oó]n de la navegaci[oó]n|igual que antes", text, re.I):
        return ESTADO_REGRESSION, "E2E de que la pantalla no se rompe: lo cubre la regresión por componente"
    if case.tipo == "TTF" and is_key_config_scenario(case.titulo, text):
        return ESTADO_QA, "TTF basado en llaves: QC no lo reproduce sin tocar configuración"
    if _OTHER_OP.search(text) and not re.search(r"error en pantalla|mensaje de error", text, re.I):
        return ESTADO_TECH, "variante de otra operación o enable=false que exige cambiar el ambiente"
    if case.tipo == "TTF" and not _STATE.search(text) and not re.search(r"error en pantalla|mensaje de error", text, re.I):
        return ESTADO_TECH, "TTF cuyo resultado no se ve en pantalla"
    if len(re.findall(r"\busuario\b", case.titulo, re.I)) >= 3:
        return ESTADO_TECH, "título ilegible; no entra al paquete"
    return None


def _merge_key(case: DesignedCase) -> tuple[str, str, str]:
    if case.tipo == "ERG":
        return ("ERG", "componente", visible_state(case) or "visual")
    return (case.tipo, _norm(user_label(case)), visible_state(case))


def _merge_group(group: list[DesignedCase]) -> DesignedCase:
    primary = group[0]
    extra = []
    for case in group[1:]:
        extra.append(
            {
                "condicion": f"opcional: vía de entrada distinta ({case.titulo})",
                "resultado_esperado": case.pasos[-1]["resultado_esperado"] if case.pasos else visible_state(case),
            }
        )
        for variant in case.variantes:
            extra.append(variant)
    merged_vars = (primary.variantes + extra)[:3]
    return replace(primary, variantes=merged_vars, titulo=rewrite_title(primary))


def behavior_ceiling(bundle: EpicBundle) -> int:
    titles = {_norm(item.title) for story in bundle.technical_stories for item in story.scenarios if item.title}
    return max(len(titles), 1)


def consolidate(
    cases: list[DesignedCase],
    bundle: EpicBundle,
    scenarios: list[Scenario],
) -> tuple[list[DesignedCase], list[dict[str, str]]]:
    discarded: list[dict[str, str]] = []
    kept: list[DesignedCase] = []
    by_id = {s.id: s for s in scenarios}

    def row(case: DesignedCase, estado: str, motivo: str) -> dict[str, str]:
        scenario = by_id.get(case.scenario_id)
        return {
            "story": bundle.key,
            "epic": bundle.key,
            "scenario": f"{case.scenario_id} {case.titulo}"[:300],
            "estado": estado,
            "case_id": "",
            "motivo": motivo,
        }

    working: list[DesignedCase] = []
    for case in cases:
        reason = _discard_reason(case)
        if reason:
            discarded.append(row(case, reason[0], reason[1]))
            continue
        prepared = _cap_variants(_trim_regression_steps(_relabel(case)), bundle)
        reason = _discard_reason(prepared)
        if reason:
            discarded.append(row(prepared, reason[0], reason[1]))
            continue
        working.append(prepared)

    groups: dict[tuple[str, str, str], list[DesignedCase]] = {}
    order: list[tuple[str, str, str]] = []
    for case in working:
        key = _merge_key(case)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(case)
    merged = [_merge_group(groups[key]) for key in order]

    cap = behavior_ceiling(bundle)
    if len(merged) > cap:
        overflow = merged[cap:]
        merged = merged[:cap]
        for case in overflow:
            discarded.append(row(case, ESTADO_HPA, "techo: comportamientos distintos de las Technical Stories"))

    finalized = []
    for case in merged:
        priority, display = assign_priority(case)
        titled = replace(case, prioridad=priority, titulo=_trim_title(case.titulo or rewrite_title(case)))
        titled.review_reasons = validate_case(titled)
        titled.complejidad = complexity(titled)
        if display:
            titled.riesgo = f"Major. {titled.riesgo}".strip()
        finalized.append(titled)
    return finalized, discarded
