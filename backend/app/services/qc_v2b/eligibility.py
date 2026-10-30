"""Elegibilidad QC previa a la IA: el tester reproduce desde el dispositivo, con cuentas reales.

Lo descartado no se pierde: cada ítem/escenario queda con estado y motivo para Escenarios de Jira.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from app.services.qc_candidate_rules import is_key_config_scenario, is_out_of_qc_inventory
from app.services.qc_v2.collect import EpicBundle, Item, TechStory, UserStory
from app.services.qc_v2.stages import Scenario

ESTADO_QA = "verificación técnica / QA"
ESTADO_TECH = "verificación técnica"
ESTADO_HPA = "variable / fuera de paquete QC"
ESTADO_REGRESSION = "fuera del paquete (regresión por componente)"
ESTADO_PACK = "paquete QC"


@dataclass(frozen=True)
class Decision:
    eligible: bool
    estado: str
    motivo: str


_FLAG_OR_KEY = re.compile(
    r"llave|apa/metadata|appkeys?|home_cdn_config|feature flag|module_version|"
    r"enable\s*=\s*false|by_user_type|metadata",
    re.IGNORECASE,
)
_NEEDS_CONFIG_CHANGE = re.compile(
    r"modificar (la )?llave|cambiar (el )?flag|habilitar en apa|"
    r"alta de llaves|construcci[oó]n de (la |las )?llaves?",
    re.IGNORECASE,
)
_SERVICE_ONLY = re.compile(
    r"\b(api|endpoint|status code|response body|payload|network|"
    r"registro en logs|el servicio responde|invoca GET|invoca POST)\b",
    re.IGNORECASE,
)
_VISIBLE = re.compile(
    r"se muestra|no se muestra|visualiza|oculta|repleg|despleg|mensaje de error|"
    r"error en pantalla|pantalla|banner|modal|bot[oó]n|home",
    re.IGNORECASE,
)
_HPA = re.compile(
    r"\b(atr[aá]s|regresar del detalle|cancelar|reintento|reintentar|"
    r"recargar la p[aá]gina|persistencia|salir y volver)\b",
    re.IGNORECASE,
)
_E2E_SAFE = re.compile(
    r"no se rompe|igual que antes|conservaci[oó]n de la navegaci[oó]n|"
    r"recorrer el men[uú] principal|el componente no se rompe",
    re.IGNORECASE,
)
_TTF_KEY = re.compile(r"llave (ausente|vac[ií]a|inexistente)|no se logra obtener una llave", re.IGNORECASE)
_OTHER_OP_SETUP = re.compile(
    r"otra operaci[oó]n|operaci[oó]n distinta|enable\s*=\s*false",
    re.IGNORECASE,
)
_ALREADY_IN_ENV = re.compile(
    r"ya (se encuentra|est[aá]|existe) (habilitad|deshabilitad|en el ambiente|en la operaci[oó]n)",
    re.IGNORECASE,
)
_THEN_LINE = re.compile(r"(?im)^\s*(?:Then|Entonces|And|Y)\s+(.+)$")
_TECH_RESULT = re.compile(
    r"par[aá]metro|payload|response body|status codes?|\bAPI\b|\bendpoint\b|"
    r"respuesta (del |de la )?(servicio|api|backend)|"
    r"nombres? de campo|campo t[eé]cnico|\bJSON\b|\bheader\b|"
    r"se obtiene el par[aá]metro",
    re.IGNORECASE,
)
_ENTRY_VISIBLE = re.compile(
    r"\b(home|nodo inicio|landing|perfiles?|selector de perfil)\b",
    re.IGNORECASE,
)
_ENTRY_ONLY = re.compile(
    r"\b(registro( de una nueva cuenta)?|inicio de sesi[oó]n|cierre de sesi[oó]n|"
    r"log\s?in|sesi[oó]n previa activa|sesi[oó]n activa|"
    r"autenticaci[oó]n( por tipo de usuario)?)\b",
    re.IGNORECASE,
)
_BEHAVIOR = re.compile(
    r"centro|notificacion|banner|modal|checkout|player|carrusel|men[uú]|"
    r"despleg|repleg|ocult|espaciado|dise[nñ]o",
    re.IGNORECASE,
)


def _blob(title: str, body: str = "") -> str:
    return f"{title}\n{body}"


def _then_clauses(body: str) -> list[str]:
    found = [m.group(1).strip() for m in _THEN_LINE.finditer(body or "")]
    return found or ([body] if body else [])


def _legacy_discards(title: str, body: str) -> Decision | None:
    from app.services.gherkin_coverage import _non_qc_inventory_reason

    reason = _non_qc_inventory_reason(title, body, None)
    if not reason:
        return None
    estado = ESTADO_QA if any(token in reason.lower() for token in ("llave", "flag", "config")) else ESTADO_TECH
    return Decision(False, estado, reason)


def _entry_only_title(title: str) -> bool:
    text = (title or "").strip()
    if not text or not _ENTRY_ONLY.search(text):
        return False
    return not _BEHAVIOR.search(text)


def _mixed_then_is_entry(body: str) -> bool:
    clauses = _then_clauses(body)
    if not clauses:
        return False
    tech = [c for c in clauses if _TECH_RESULT.search(c)]
    visible = [c for c in clauses if _VISIBLE.search(c) or _ENTRY_VISIBLE.search(c)]
    if not tech:
        return False
    if not visible:
        return True
    return all(_ENTRY_VISIBLE.search(c) and not _BEHAVIOR.search(c) for c in visible)


def expected_has_technical_leak(text: str) -> bool:
    return bool(_TECH_RESULT.search(text or ""))


def classify_text(title: str, body: str = "") -> Decision:
    text = _blob(title, body)
    legacy = _legacy_discards(title, body)
    if legacy:
        return legacy
    if _entry_only_title(title):
        return Decision(
            False,
            ESTADO_TECH,
            "forma de entrar (registro/login/sesión); se usa como precondición, no como caso",
        )
    if _mixed_then_is_entry(body) or (_TECH_RESULT.search(text) and not _BEHAVIOR.search(text)):
        return Decision(
            False,
            ESTADO_TECH,
            "Then técnico (parámetro/API/servicio); lo visible es solo llegar a Home o perfiles",
        )
    if is_out_of_qc_inventory(title, body) or is_key_config_scenario(title, body) or _TTF_KEY.search(text):
        return Decision(False, ESTADO_QA, "requiere modificar llaves/metadata/flags o la llave está ausente/vacía")
    if _NEEDS_CONFIG_CHANGE.search(text) or (_FLAG_OR_KEY.search(text) and not _VISIBLE.search(text)):
        return Decision(False, ESTADO_QA, "requiere modificar llaves/metadata/flags; QC no lo reproduce desde el dispositivo")
    if _SERVICE_ONLY.search(text) and not _VISIBLE.search(text):
        return Decision(False, ESTADO_TECH, "el resultado no se ve en pantalla (API, logs o respuesta de servicio)")
    if _OTHER_OP_SETUP.search(text) and not _ALREADY_IN_ENV.search(text) and not _VISIBLE.search(text):
        return Decision(
            False,
            ESTADO_TECH,
            "variante de configuración (otra operación o enable=false) que exige cambiar el ambiente",
        )
    if _E2E_SAFE.search(text):
        return Decision(False, ESTADO_REGRESSION, "E2E de que la pantalla no se rompe: lo cubre la regresión por componente")
    if _HPA.search(title) and not _VISIBLE.search(title):
        return Decision(False, ESTADO_HPA, "HPA de navegación (atrás, cancelar, reintento, recargar, persistencia)")
    return Decision(True, ESTADO_PACK, "QC lo reproduce desde el dispositivo con cuentas reales")


def classify_item(item: Item) -> Decision:
    return classify_text(item.title, item.text)


def classify_scenario(scenario: Scenario) -> Decision:
    conditions = "; ".join(scenario.condiciones)
    return classify_text(scenario.titulo, f"{scenario.descripcion}\n{conditions}")


def ledger_row(bundle: EpicBundle, item: Item, decision: Decision) -> dict[str, str]:
    return {
        "story": item.source_key,
        "epic": bundle.key,
        "scenario": f"{item.id} {item.title}"[:300],
        "estado": decision.estado,
        "case_id": "",
        "motivo": decision.motivo,
    }


def filter_bundle(bundle: EpicBundle) -> tuple[EpicBundle, list[dict[str, str]]]:
    discarded: list[dict[str, str]] = []

    def keep_items(items: list[Item]) -> list[Item]:
        kept: list[Item] = []
        for item in items:
            decision = classify_item(item)
            if decision.eligible:
                kept.append(item)
            else:
                discarded.append(ledger_row(bundle, item, decision))
        return kept

    technical = [
        TechStory(story.key, story.summary, story.context, keep_items(story.scenarios))
        for story in bundle.technical_stories
    ]
    users: list[UserStory] = []
    for story in bundle.user_stories:
        users.append(
            replace(story, criteria=keep_items(story.criteria)),
        )
    return replace(bundle, technical_stories=technical, user_stories=users), discarded
