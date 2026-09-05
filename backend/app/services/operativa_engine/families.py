"""BRF family classification from current evidence. Historical families are patterns, not copied values."""

from __future__ import annotations

import re

from app.services.operativa_engine.devices import normalize_blob

FAMILY_INFRA = "INFRA"
FAMILY_REPORTS = "REPORTS"
FAMILY_OFFER = "OFFER"
FAMILY_CHANNEL = "CHANNEL"
FAMILY_CAROUSEL = "CAROUSEL"
FAMILY_IDENTITY = "IDENTITY"
FAMILY_SIGNAL_OFF = "SIGNAL_OFF"
FAMILY_MDP = "MDP"
FAMILY_GENERIC = "GENERIC"


def classify_family(title: str, extra: str = "") -> str:
    blob = normalize_blob(f"{title} {extra}").lower()
    compact = re.sub(r"\s+", "", blob)
    if _has(blob, compact, "whitelist", "vpn", "pincode", "pincode", "ftp", "apim",
            "servidor", "infra", "lote", "contenidodeprue", "contenido de prue"):
        return FAMILY_INFRA
    if _has(blob, compact, "reporte", "reportes", "métrica", "metrica", "analytics"):
        return FAMILY_REPORTS
    if _has(blob, compact, "medio de pago", "medios de pago", "mdp") and "oferta" not in compact:
        return FAMILY_MDP
    if _has(
        blob, compact,
        "dar de baja canal", "baja canal", "baja de canal", "eliminar canal",
        "dar de baja", "señalestv", "baja de can",
    ) and "ftp" not in compact:
        return FAMILY_SIGNAL_OFF
    if _has(blob, compact, "carrusel"):
        return FAMILY_CAROUSEL
    if (
        ("canal" in blob or "canales" in blob)
        and any(token in blob for token in ("alta de", "alta del", "alta el", "alta los"))
    ) or _has(
        blob, compact,
        "canal américa", "canal america", "plim plim",
        "timeshift", "npvr", "tv everywhere",
    ):
        return FAMILY_CHANNEL
    if _has(blob, compact, "nombre y logo", "actualizar logo", "actualizar nombre", "logotipo"):
        return FAMILY_IDENTITY
    if _has(
        blob, compact,
        "oferta", "add on", "add-on", "addon", "type 1", "type finde",
        "type est", "contrat", "renta",
    ):
        return FAMILY_OFFER
    return FAMILY_GENERIC


def _has(blob: str, compact: str, *tokens: str) -> bool:
    for token in tokens:
        if token in blob or token.replace(" ", "") in compact:
            return True
    return False
