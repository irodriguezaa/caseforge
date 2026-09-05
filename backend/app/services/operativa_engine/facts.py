"""Structured functional extract. Extract first; group into behaviors later. Never invent values."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.operativa_engine.hn import HistoriaNegocio

_INTERACTION_POINT_TOKENS = (
    "plan selector",
    "landing comercial",
    "landing",
    "vcard",
    "checkout",
    "ticket",
    "home",
    "mi cuenta",
    "suscripción",
    "suscripcion",
    "epg full",
    "epg mini",
    "player live",
    "panel de opciones",
    "mosaico",
    "buscador",
    "timeshift",
    "npvr",
    "tv everywhere",
    "carrusel",
)

_GROUP_ID_RE = re.compile(
    r"\bgroup\s*id\b\s*[:#=\-]?\s*([A-Za-z0-9._\-]+)",
    re.IGNORECASE,
)
_PRICE_LINE_RE = re.compile(
    r"(?:precio(?:s)?(?:\s+por\s+dispositivo)?|price)\s*[:\-]\s*([^\n]{2,120})",
    re.IGNORECASE,
)
_MONEY_RE = re.compile(r"(?:USD|MXN|COP|PEN|CLP|ARS|GTQ|HNL|NIO|CRC|PAB|DOP|\$)\s*[\d.,]+", re.IGNORECASE)
_CHANNEL_LINE_RE = re.compile(
    r"(?:^|\n)\s*(?:canal|channel)\s*[:.]?\s*(\d{1,4})\s*[-:–]\s*([^\n|;]{2,80})",
    re.IGNORECASE,
)
_CHANNEL_NAME_NUM_RE = re.compile(
    r"([A-Za-zÁÉÍÓÚÑáéíóúñ0-9 .+/]{2,40})\s*[–\-]\s*(?:n(?:ú|u)m(?:ero)?(?:\s+de)?\s*canal|ch(?:annel)?)\s*[:#]?\s*(\d{1,4})",
    re.IGNORECASE,
)


@dataclass
class FunctionalFacts:
    offer_label: str | None = None
    offer_type: str | None = None
    group_id: str | None = None
    prices: list[str] = field(default_factory=list)
    currency: str | None = None
    acquisition: list[str] = field(default_factory=list)
    trailer: bool = False
    download: bool = False
    ho: bool = False
    mdp: list[str] = field(default_factory=list)
    users: list[str] = field(default_factory=list)
    interaction_points: list[str] = field(default_factory=list)
    channels: list[str] = field(default_factory=list)
    negatives: list[str] = field(default_factory=list)
    case_insensitive_search: bool = False
    hn_source: str = "HN_ABSENT"
    hn_keys: list[str] = field(default_factory=list)

    def test_data_lines(self) -> list[str]:
        lines: list[str] = []
        if self.group_id:
            lines.append(f"Group ID: {self.group_id}")
        if self.offer_type:
            lines.append(f"Tipo de oferta: {self.offer_type}")
        if self.prices:
            lines.append("Precios: " + "; ".join(self.prices))
        if self.currency:
            lines.append(f"Moneda: {self.currency}")
        if self.acquisition:
            lines.append("Modalidad: " + ", ".join(self.acquisition))
        if self.mdp:
            lines.append("MDP: " + ", ".join(self.mdp))
        if self.channels:
            lines.append("Canales: " + "; ".join(self.channels))
        if self.interaction_points:
            lines.append("Canal / Punto de interacción: " + ", ".join(self.interaction_points))
        if self.users:
            lines.append("Usuario: " + ", ".join(self.users))
        return lines


def extract_functional_facts(
    *,
    title: str,
    evidence: str,
    historias: list[HistoriaNegocio],
) -> FunctionalFacts:
    blob = "\n".join(part for part in (title, evidence) if part)
    lowered = blob.lower()
    hn_keys = [item.key for item in historias]
    if hn_keys:
        hn_source = "HN_PRESENT"
    elif any(token in lowered for token in ("hn ausente", "sin hn", "hn/ca no disponible")):
        hn_source = "HN_ABSENT"
    else:
        hn_source = "HN_ABSENT" if not historias else "PARTIAL"

    group_match = _GROUP_ID_RE.search(blob)
    prices = _unique(_PRICE_LINE_RE.findall(blob) + _MONEY_RE.findall(blob))
    acquisition = []
    if re.search(r"\bcompra\b", lowered):
        acquisition.append("compra")
    if re.search(r"\brenta\b", lowered):
        acquisition.append("renta")

    mdp = _unique(
        token
        for token in (
            "Visa", "Mastercard", "Amex", "PayPal", "PayU", "Daviplata",
            "Nequi", "PSE", "Google Play", "App Store", "Roku Pay", "Claro Recarga",
        )
        if token.lower() in lowered
    )

    users = []
    if "no suscrit" in lowered or "sin suscrip" in lowered:
        users.append("No suscrito")
    if "suscrit" in lowered or "registrad" in lowered:
        users.append("Suscrito")

    tokens = [label for label in _INTERACTION_POINT_TOKENS if label in lowered]
    interaction_labels = [_interaction_point_label(item) for item in tokens]

    channels = _extract_channels(blob)
    negatives = []
    for item in historias:
        if item.is_negative:
            negatives.append(_negative_subject(item.text, title))
    if not negatives:
        for match in re.finditer(
            r"no\s+(?:habilitar|publicar|liberar|incluir)\s+([^\n.]{3,80})",
            lowered,
        ):
            negatives.append(match.group(0).strip())

    offer_type = None
    type_match = re.search(r"\btype\s+([A-Z0-9][A-Z0-9 ._-]{1,40})", title, re.IGNORECASE)
    if type_match:
        offer_type = "Type " + type_match.group(1).strip()

    return FunctionalFacts(
        offer_label=_offer_label(title, offer_type),
        offer_type=offer_type,
        group_id=(group_match.group(1).strip().rstrip(".,;") if group_match else None),
        prices=prices[:8],
        currency=_currency(blob),
        acquisition=acquisition,
        trailer="trailer" in lowered,
        download=any(token in lowered for token in ("descarga", "download")),
        ho=bool(re.search(r"\bHO\b|home office", blob)),
        mdp=mdp,
        users=_unique(users),
        interaction_points=_unique(interaction_labels),
        channels=channels,
        negatives=_unique(negatives),
        case_insensitive_search=any(
            token in lowered
            for token in (
                "independiente de mayúsculas",
                "independiente de mayusculas",
                "case insensitive",
                "no distingue mayúsculas",
                "no distingue mayusculas",
            )
        ),
        hn_source=hn_source,
        hn_keys=hn_keys,
    )


def _offer_label(title: str, offer_type: str | None) -> str | None:
    cleaned = re.sub(r"\s+", " ", title or "").strip()
    if not cleaned:
        return offer_type
    return cleaned[:160]


def _currency(blob: str) -> str | None:
    match = re.search(r"\b(USD|MXN|COP|PEN|CLP|ARS|GTQ|HNL|NIO|CRC|PAB|DOP)\b", blob, re.IGNORECASE)
    return match.group(1).upper() if match else None


def _extract_channels(blob: str) -> list[str]:
    found: list[str] = []
    for match in _CHANNEL_LINE_RE.finditer(blob):
        found.append(f"{match.group(1)} — {match.group(2).strip()}")
    for match in _CHANNEL_NAME_NUM_RE.finditer(blob):
        found.append(f"{match.group(2)} — {match.group(1).strip()}")
    return _unique(found)[:40]


def _negative_subject(text: str, title: str) -> str:
    match = re.search(
        r"no\s+(?:habilitar|publicar|liberar|incluir)\s+(.+)",
        text,
        re.IGNORECASE,
    )
    if match:
        return match.group(0).strip()[:160]
    return (title or text)[:160]


def _interaction_point_label(token: str) -> str:
    mapping = {
        "plan selector": "Plan Selector",
        "landing comercial": "Landing Comercial",
        "landing": "Landing",
        "vcard": "vCard",
        "checkout": "Checkout",
        "ticket": "Ticket",
        "home": "Home",
        "mi cuenta": "Mi cuenta",
        "suscripción": "Suscripción",
        "suscripcion": "Suscripción",
        "epg full": "EPG Full",
        "epg mini": "EPG Mini",
        "player live": "Player Live",
        "panel de opciones": "Panel de Opciones",
        "mosaico": "Mosaico",
        "buscador": "Buscador",
        "timeshift": "Timeshift",
        "npvr": "NPVR",
        "tv everywhere": "TV Everywhere",
        "carrusel": "Carrusel",
    }
    return mapping.get(token, token)


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = re.sub(r"\s+", " ", value).strip()
        if not key:
            continue
        lowered = key.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        out.append(key)
    return out
