"""Classify every HN before behaviors exist. No offer-template (Alta+MDP+Comunicación)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.operativa_engine.hn import HistoriaNegocio, hn_title

PRIMARY = "PRIMARY_BEHAVIOR"
SUPPORTING = "SUPPORTING"
SCENARIO = "SCENARIO"
TEST_DATA = "TEST_DATA"
DEPENDENCY_CONFIGURATION = "DEPENDENCY_CONFIGURATION"
OOS_QC = "OOS_QC"

_FUNCTIONAL_CONFIG_TOKENS = (
    "compra",
    "renta",
    "descarga",
    "download",
    "trailer",
    "preview",
    "precio",
    "group id",
    "id group",
    "tipo de oferta",
    "type ",
    "modelo de negocio",
    "especificaci",
)
_YES_NO_RE = re.compile(
    r"(compra|renta|descarga|download|preview(?:\s*/\s*trailer)?|trailer|ho)\s*[=:]\s*(s[ií]|no|yes|true|false)",
    re.IGNORECASE,
)
_GROUP_ID_RE = re.compile(
    r"(?:group\s*id|id\s*group|id group)\s*[=:#\-]?\s*([A-Za-z0-9._\-]+)",
    re.IGNORECASE,
)
_SCENARIO_TITLE_RE = re.compile(
    r"usuario\s+(?:no\s+)?suscrit|sin suscripci|suscripci[oó]n desde|"
    r"compra y renta|s[oó]lo compra|solo renta",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class HnDisposition:
    key: str
    disposition: str
    reason: str
    related_to: str | None = None


def classify_historias(items: list[HistoriaNegocio]) -> dict[str, HnDisposition]:
    raw: dict[str, HnDisposition] = {}
    for item in items:
        disposition, reason = _classify_one(item)
        raw[item.key] = HnDisposition(key=item.key, disposition=disposition, reason=reason)
    related = _relate(items, raw)
    return {
        key: HnDisposition(
            key=key,
            disposition=item.disposition,
            reason=item.reason,
            related_to=related.get(key),
        )
        for key, item in raw.items()
    }


def attached_to(primary_key: str, classified: dict[str, HnDisposition]) -> list[str]:
    return [key for key, item in classified.items() if item.related_to == primary_key]


def primary_keys(classified: dict[str, HnDisposition]) -> list[str]:
    return [key for key, item in classified.items() if item.disposition == PRIMARY]


def _classify_one(item: HistoriaNegocio) -> tuple[str, str]:
    title = hn_title(item.text)
    lowered = title.lower()
    body = item.text.lower()

    if item.is_report or re.search(r"\breportes?\b|\bm[eé]tricas?\b|\bbusiness intelligence\b", lowered):
        return OOS_QC, "Reportes/métricas fuera de QC. Se conserva trazabilidad; no genera TC."
    if item.is_test_content or _looks_like_test_data(title, body):
        return TEST_DATA, "Datos de ejecución/contenido de prueba. Alimentan Test Data; no generan TC propios."
    if item.superseded:
        return SUPPORTING, (
            f"Sustituida por {item.updates or 'HN posterior'}. "
            "El criterio vigente vive en la HN modificadora."
        )
    if any(
        token in lowered
        for token in (
            "insumos de diseño",
            "insumos de diseno",
            "compartir insumos",
            "obtener las plantillas",
            "plantillas de comunicación",
            "plantillas de comunicacion",
        )
    ):
        return DEPENDENCY_CONFIGURATION, "Insumo/plantilla de diseño: dependencia, no comportamiento user-facing."
    if "mantener" in lowered:
        return SCENARIO, (
            "HN de impacto/mantener: no se parte en un TC por capacidad. "
            "Se adjunta al comportamiento relacionado o queda para decisión QC."
        )
    if _is_config_title(lowered):
        if _has_functional_config(body, title):
            return SUPPORTING, (
                "Valores de configuración con criterio funcional observable. "
                "Complementan el comportamiento primario; no son un TC de 'configuración'."
            )
        return DEPENDENCY_CONFIGURATION, (
            "Configuración técnica sin criterio user-facing suficiente (p. ej. Resource ID)."
        )
    if _SCENARIO_TITLE_RE.search(title) and not _looks_like_primary_capability(lowered):
        return SCENARIO, "Escenario de uso (usuario/acceso/modalidad). Se evalúa sobre el comportamiento relacionado."
    return PRIMARY, "Capacidad funcional verificable. Unidad de comportamiento, no de template Alta/MDP/Comunicación."


def _looks_like_test_data(title: str, body: str) -> bool:
    blob = f"{title} {body}".lower()
    return any(
        token in blob
        for token in (
            "compartir contenido",
            "contenido para validaciones",
            "contenido de prueba",
            "datos de prueba",
            "id program",
            "id programa",
        )
    )


def _is_config_title(title: str) -> bool:
    return any(
        token in title
        for token in (
            "valores de configuración",
            "valores de configuracion",
            "configuración",
            "configuracion",
            "resource id",
            "resourceid",
        )
    ) and not _looks_like_primary_capability(title)


def _has_functional_config(body: str, title: str) -> bool:
    blob = f"{title} {body}".lower()
    if _YES_NO_RE.search(blob):
        return True
    return any(token in blob for token in _FUNCTIONAL_CONFIG_TOKENS)


def _looks_like_primary_capability(title: str) -> bool:
    return any(
        token in title
        for token in (
            "alta",
            "disponib",
            "contrat",
            "medio de pago",
            "medios de pago",
            "comunicaci",
            "checkout",
            "ticket",
            "carrusel",
            "reproduc",
            "logotipo",
            "logo",
            "nombre del canal",
            "baja",
            "no liberar",
            "no publicar",
            "no habilitar",
            "plan selector",
            "vcard",
            "landing",
            "timeshift",
            "npvr",
            "tv everywhere",
            "buscador",
            "mosaico",
            "player",
        )
    )


def _relate(items: list[HistoriaNegocio], raw: dict[str, HnDisposition]) -> dict[str, str | None]:
    primaries = [item for item in items if raw[item.key].disposition == PRIMARY]
    last_primary: str | None = primaries[0].key if primaries else None
    offer_primary = next(
        (item.key for item in primaries if _is_offer_like(hn_title(item.text))),
        last_primary,
    )
    related: dict[str, str | None] = {}
    by_key = {item.key: item for item in items}

    for item in items:
        disp = raw[item.key].disposition
        if disp == PRIMARY:
            last_primary = item.key
            if _is_offer_like(hn_title(item.text)):
                offer_primary = item.key
            related[item.key] = None
            continue
        if disp == OOS_QC:
            related[item.key] = None
            continue
        if item.updates and item.updates in by_key:
            updater = item.key
            target = updater if raw.get(updater) and raw[updater].disposition == PRIMARY else offer_primary
            # superseded HN relates to the HN that replaced it
            related[item.key] = item.updates if raw[item.updates].disposition == PRIMARY else target
            continue
        if disp in {SUPPORTING, SCENARIO, TEST_DATA, DEPENDENCY_CONFIGURATION}:
            related[item.key] = offer_primary or last_primary
            continue
        related[item.key] = None

    for item in items:
        if not item.superseded:
            continue
        modifier = next((other.key for other in items if other.updates == item.key), None)
        related[item.key] = modifier or offer_primary or last_primary

    # Promote supporting-with-criteria when nothing primary exists.
    if not primaries:
        for item in items:
            if raw[item.key].disposition == SUPPORTING and _has_functional_config(item.text, hn_title(item.text)):
                raw[item.key] = HnDisposition(
                    key=item.key,
                    disposition=PRIMARY,
                    reason="No hay HN PRIMARY; esta HN de configuración contiene el criterio funcional observable.",
                )
                related[item.key] = None
                for other in items:
                    if related.get(other.key) is None and raw[other.key].disposition != PRIMARY:
                        if raw[other.key].disposition in {SUPPORTING, SCENARIO, TEST_DATA, DEPENDENCY_CONFIGURATION}:
                            related[other.key] = item.key
                break
        else:
            for item in items:
                if raw[item.key].disposition == SCENARIO:
                    raw[item.key] = HnDisposition(
                        key=item.key,
                        disposition=PRIMARY,
                        reason="HN de escenario/impacto sin comportamiento primario compañero; QC confirma cobertura.",
                    )
                    related[item.key] = None
                    break
    return related


def _is_offer_like(title: str) -> bool:
    lowered = title.lower()
    return any(token in lowered for token in ("alta", "oferta", "add-on", "add on", "disponib", "type "))


def extract_supporting_facts(blob: str) -> list[str]:
    """Structured criteria from supporting/test-data HNs. Never invents values."""
    lines: list[str] = []
    seen: set[str] = set()

    def add(line: str) -> None:
        if line and line not in seen:
            seen.add(line)
            lines.append(line)

    for match in _YES_NO_RE.finditer(blob or ""):
        label = match.group(1).strip().capitalize()
        value = match.group(2).strip()
        normalized = "Sí" if value.lower() in {"si", "sí", "yes", "true"} else "No"
        add(f"{label}: {normalized}")
    group = _GROUP_ID_RE.search(blob or "")
    if group:
        add(f"Group ID: {group.group(1).strip()}")
    # ID program/catalog ids stay in the HN extract (trazabilidad); QC ejecuta con Group ID.
    supplier = re.search(r"supplier\s*[=:]\s*([^\n|;]+)", blob or "", re.I)
    if supplier:
        add("Supplier: " + supplier.group(1).strip())
    region = re.search(r"regi[oó]n\s*[=:]\s*([^\n|;]+)", blob or "", re.I)
    if region:
        add("Región: " + region.group(1).strip())
    until = re.search(r"hasta\s*[=:]\s*([^\n|;]+)", blob or "", re.I)
    if until:
        add("Hasta: " + until.group(1).strip())
    title = re.search(r"t[ií]tulo\s*[=:]\s*([^\n|;]+)", blob or "", re.I)
    if title and "prueba" in title.group(1).lower():
        add("Título de prueba: " + title.group(1).strip())
    return lines
