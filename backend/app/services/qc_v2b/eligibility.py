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


def _blob(title: str, body: str = "") -> str:
    return f"{title}\n{body}"


def classify_text(title: str, body: str = "") -> Decision:
    text = _blob(title, body)
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
