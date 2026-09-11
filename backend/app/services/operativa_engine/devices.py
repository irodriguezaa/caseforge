"""Ecosystem vs device. QC execution matrices are knowledge, not per-BRF catalogs."""

from __future__ import annotations

import re
from dataclasses import dataclass

ECOSYSTEM_OTT = "OTT"
ECOSYSTEM_IPTV = "IPTV"
PENDING_DEVICE = "PENDING"
SOURCE_OTT_MATRIX = "matriz QC de ejecución OTT"
SOURCE_IPTV_MATRIX = "matriz QC de ejecución IPTV"

# Android in Operativas is three different things:
#   Android            → ADR (OTT móvil)
#   Android TV para STV → ADT (OTT smart TV con Android; no es STB)
#   STB (Android TV)    → STB (IPTV por definición)
QC_OTT_EXECUTION_MATRIX: tuple[str, ...] = (
    "WEB",
    "AAF",
    "ADR",
    "iOS",
    "tvOS",
    "Windows/XBOX",
    "Consolas",
    "Roku",
    "Fire TV",
    "ADT",
)
QC_IPTV_EXECUTION_MATRIX: tuple[str, ...] = ("STB",)

DEVICE_ALIASES: dict[str, str] = {
    "web": "WEB",
    "desktop": "WEB",
    "android": "ADR",
    "android mobile": "ADR",
    "mobile android": "ADR",
    "adr": "ADR",
    "ios": "iOS",
    "iphone": "iOS",
    "ipad": "iOS",
    "tvos": "tvOS",
    "roku": "Roku",
    "firetv": "Fire TV",
    "fire tv": "Fire TV",
    "aaf": "AAF",
    "aaf evolutivo": "AAF",
    "stb": "STB",
    "stb iptv": "STB",
    "stb aosp": "STB",
    "stb (aosp, android tv)": "STB",
    "stb (android tv)": "STB",
    "stb android tv": "STB",
    "android tv stv": "ADT",
    "android tv para stv": "ADT",
    "android tv": "ADT",
    "adt": "ADT",
    "consolas": "Consolas",
    "consola": "Consolas",
    "windows": "Windows/XBOX",
    "xbox": "Windows/XBOX",
    "win/xbox": "Windows/XBOX",
    "windows/xbox": "Windows/XBOX",
    "kepler": "Kepler",
    "coship": "STB",
    "coship 9085": "STB",
    "coship9085": "STB",
}

_MENTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bandroid\s*tv\s*(para\s*)?stv\b", re.I), "ADT"),
    (re.compile(r"\bstb\s*\(\s*android\s*tv\s*\)", re.I), "STB"),
    (re.compile(r"\bstb\s*\(?\s*aosp", re.I), "STB"),
    (re.compile(r"\bstb\s*iptv\b", re.I), "STB"),
    (re.compile(r"\bfire\s*tv\b", re.I), "Fire TV"),
    (re.compile(r"\baaf\s+evolutivo\b", re.I), "AAF"),
    (re.compile(r"\bwin\s*/\s*xbox\b", re.I), "Windows/XBOX"),
    (re.compile(r"\bwindows\s*/\s*xbox\b", re.I), "Windows/XBOX"),
    (re.compile(r"\bmobile\s+android\b", re.I), "ADR"),
    (re.compile(r"\bandroid\s+mobile\b", re.I), "ADR"),
    (re.compile(r"\bconsolas?\b", re.I), "Consolas"),
    (re.compile(r"\bandroid\s*tv\b", re.I), "ADT"),
    (re.compile(r"\bandroid\b", re.I), "ADR"),
    (re.compile(r"\bwindows\b", re.I), "Windows/XBOX"),
    (re.compile(r"\bxbox\b", re.I), "Windows/XBOX"),
    (re.compile(r"\bkepler\b", re.I), "Kepler"),
    (re.compile(r"\bfiretv\b", re.I), "Fire TV"),
    (re.compile(r"\btvos\b", re.I), "tvOS"),
    (re.compile(r"\biphone\b|\bipad\b|\bios\b", re.I), "iOS"),
    (re.compile(r"\broku\b", re.I), "Roku"),
    (re.compile(r"\baaf\b", re.I), "AAF"),
    (re.compile(r"\bstb\b", re.I), "STB"),
    (re.compile(r"\badr\b", re.I), "ADR"),
    (re.compile(r"\badt\b", re.I), "ADT"),
    (re.compile(r"\bdesktop\b", re.I), "WEB"),
    (re.compile(r"\bweb\b", re.I), "WEB"),
]

_LABELED_DEVICES = re.compile(
    r"(?:dispositivos?|plataformas?|devices?|aplicabilidad|plataformas?\s+impactadas?)"
    r"\s*[:\-]\s*([^\n]+)",
    re.IGNORECASE,
)

OTT_DEVICES = set(QC_OTT_EXECUTION_MATRIX) | {"Kepler"}
IPTV_DEVICES = set(QC_IPTV_EXECUTION_MATRIX)


@dataclass(frozen=True)
class DeviceTarget:
    label: str
    ecosystem: str | None
    source: str = ""
    applicability_reason: str = ""


def normalize_blob(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def is_pending_device(label: str | None) -> bool:
    return (label or "").upper() == PENDING_DEVICE


def ecosystem_of(device_label: str) -> str | None:
    if is_pending_device(device_label):
        return None
    if device_label in IPTV_DEVICES:
        return ECOSYSTEM_IPTV
    if device_label in OTT_DEVICES:
        return ECOSYSTEM_OTT
    return None


def ott_matrix(*, reason: str = "BRF declara ecosistema OTT") -> list[DeviceTarget]:
    return [
        DeviceTarget(
            label=label,
            ecosystem=ECOSYSTEM_OTT,
            source=SOURCE_OTT_MATRIX,
            applicability_reason=reason,
        )
        for label in QC_OTT_EXECUTION_MATRIX
    ]


def iptv_matrix(*, reason: str = "BRF declara ecosistema IPTV") -> list[DeviceTarget]:
    return [
        DeviceTarget(
            label=label,
            ecosystem=ECOSYSTEM_IPTV,
            source=SOURCE_IPTV_MATRIX,
            applicability_reason=reason,
        )
        for label in QC_IPTV_EXECUTION_MATRIX
    ]


def candidate_universe(ott: bool, iptv: bool, *, reason: str) -> list[DeviceTarget]:
    found: list[DeviceTarget] = []
    if ott:
        found.extend(ott_matrix(reason=reason))
    if iptv:
        found.extend(iptv_matrix(reason=reason))
    return found


def parse_declared_devices(
    values: list[str] | None,
    *,
    source: str = "QC dispositivos_aplicables",
) -> list[DeviceTarget]:
    found: list[DeviceTarget] = []
    seen: set[str] = set()
    for raw in values or []:
        label = _alias_lookup(raw)
        if not label or label in seen:
            continue
        seen.add(label)
        found.append(
            DeviceTarget(
                label=label,
                ecosystem=ecosystem_of(label),
                source=source,
                applicability_reason="Selección explícita de QC (Paso 3).",
            )
        )
    return found


def infer_ecosystems(text: str) -> tuple[bool, bool]:
    blob = normalize_blob(text).lower()
    ott = bool(re.search(r"\bott\b", blob))
    iptv = bool(re.search(r"\biptv\b", blob))
    return ott, iptv


def extract_devices_from_text(text: str | None, *, source: str) -> list[DeviceTarget]:
    """Devices named in this fragment only. Does not copy another BRF."""
    blob = text or ""
    if not blob.strip():
        return []
    found: list[DeviceTarget] = []
    seen: set[str] = set()

    def add(label: str, origin: str) -> None:
        if label in seen:
            return
        seen.add(label)
        found.append(
            DeviceTarget(
                label=label,
                ecosystem=ecosystem_of(label),
                source=origin,
                applicability_reason="Dispositivo nombrado en el contenido del BRF/HN.",
            )
        )

    for match in _LABELED_DEVICES.finditer(blob):
        for token in re.split(r"[,;/]| y | e |\||\n", match.group(1)):
            label = _alias_lookup(token)
            if label:
                add(label, f"{source} (lista etiquetada)")

    masked = blob
    for pattern, label in _MENTION_PATTERNS:
        if pattern.search(masked):
            add(label, source)
            masked = pattern.sub(" ", masked)
    return found


def pending_target(*, source: str) -> DeviceTarget:
    return DeviceTarget(
        label=PENDING_DEVICE,
        ecosystem=None,
        source=source,
        applicability_reason="Sin ecosistema ni dispositivos declarados; QC debe definir aplicabilidad.",
    )


def resolve_targets(
    dispositivos_aplicables: list[str] | None,
    *text_parts: str | None,
    source: str = "BRF",
) -> tuple[list[DeviceTarget], list[str]]:
    notes: list[str] = []
    blob = "\n".join(part for part in text_parts if part)
    explicit = extract_devices_from_text(blob, source=source)
    if explicit:
        return explicit, notes
    qc = parse_declared_devices(dispositivos_aplicables)
    if qc:
        notes.append("Dispositivos tomados de la selección QC (el BRF no nombró plataformas).")
        return qc, notes
    ott, iptv = infer_ecosystems(blob)
    universe = candidate_universe(ott, iptv, reason=f"{source}: universo candidato del ecosistema declarado")
    if universe:
        notes.append(
            "Aplicabilidad: universo candidato de ejecución QC según ecosistema declarado; "
            "se recorta por comportamiento cuando hay evidencia."
        )
        return universe, notes
    notes.append("Sin ecosistema declarado y sin dispositivos nombrados.")
    return [pending_target(source=f"{source} (sin ecosistema)")], notes


def _alias_lookup(raw: str | None) -> str | None:
    key = normalize_blob(raw).lower()
    if not key or key in {"ott", "iptv", "ott e iptv", "ott y iptv"}:
        return None
    label = DEVICE_ALIASES.get(key)
    if label:
        return label
    compact = re.sub(r"[^a-z0-9]+", " ", key).strip()
    return DEVICE_ALIASES.get(compact)
