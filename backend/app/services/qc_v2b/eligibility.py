"""Elegibilidad v2-B: el filtro positivo de Legacy, más el recorte del paquete QC.

La decisión de qué es QC vive en qc_eligibility.py. Aquí solo se aplica lo propio del
paquete v2b: TTF con resultado visible, y ningún HPA de navegación.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from app.services.qc_candidate_rules import is_key_config_scenario
from app.services.qc_eligibility import evaluate_scenario
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
_TTF_KEY = re.compile(r"llave (ausente|vac[ií]a|inexistente)|no se logra obtener una llave", re.IGNORECASE)
_TECH_RESULT = re.compile(
    r"par[aá]metro|payload|response body|status codes?|\bAPI\b|\bendpoint\b|"
    r"respuesta (del |de la )?(servicio|api|backend)|"
    r"nombres? de campo|campo t[eé]cnico|\bJSON\b|\bheader\b|"
    r"se obtiene el par[aá]metro",
    re.IGNORECASE,
)
_INVISIBLE_TTF = re.compile(
    r"\b(no se (env[ií]a|registra|dispara|reporta)|status code|payload|"
    r"el servicio (no )?responde|llave (ausente|vac[ií]a))\b",
    re.IGNORECASE,
)


def _blob(title: str, body: str = "") -> str:
    return f"{title}\n{body}"


def expected_has_technical_leak(text: str) -> bool:
    return bool(_TECH_RESULT.search(text or ""))


def classify_text(title: str, body: str = "") -> Decision:
    text = _blob(title, body)
    elig = evaluate_scenario(title, body)
    if re.search(r"no se rompe|conservaci[oó]n de la navegaci[oó]n", text, re.I):
        return Decision(
            False,
            ESTADO_REGRESSION,
            "E2E de que la pantalla no se rompe: lo cubre la regresión por componente",
        )
    if not elig.ok:
        if is_key_config_scenario(title, body) or _TTF_KEY.search(text):
            return Decision(False, ESTADO_QA, elig.ledger_motivo)
        if _HPA.search(title) and not _VISIBLE.search(title):
            return Decision(False, ESTADO_HPA, elig.ledger_motivo)
        if elig.generic_regression:
            return Decision(False, ESTADO_REGRESSION, elig.ledger_motivo)
        estado = elig.ledger_estado
        if estado == "caso ejecutable":
            estado = ESTADO_TECH
        return Decision(False, estado, elig.ledger_motivo)
    if elig.generic_regression or re.search(
        r"no se rompe|conservaci[oó]n de la navegaci[oó]n", text, re.I
    ):
        return Decision(
            False,
            ESTADO_REGRESSION,
            "E2E de que la pantalla no se rompe: lo cubre la regresión por componente",
        )
    if _HPA.search(title) and not _VISIBLE.search(title):
        return Decision(
            False,
            ESTADO_HPA,
            "HPA de navegación (atrás, cancelar, reintento, recargar, persistencia)",
        )
    if _INVISIBLE_TTF.search(text) and not _VISIBLE.search(text):
        return Decision(
            False,
            ESTADO_QA if _TTF_KEY.search(text) else ESTADO_TECH,
            "TTF sin resultado visible en el dispositivo",
        )
    if expected_has_technical_leak(text):
        return Decision(
            False,
            ESTADO_TECH,
            "el resultado no se verifica mirando el dispositivo",
        )
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
