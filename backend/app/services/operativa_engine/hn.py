"""HN/CA parsing. HN is not a Test Case. Modifier HNs replace prior criteria."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.operativa_engine.devices import DeviceTarget, extract_devices_from_text, normalize_blob

_HN_RE = re.compile(
    r"(?:^|\n)\s*(HN\d{2,4})\b\s*[:.\-]?\s*(.*?)(?=(?:\n\s*HN\d{2,4}\b)|$)",
    re.IGNORECASE | re.DOTALL,
)
_CA_RE = re.compile(
    r"(?:^|\n)\s*(CA[- ]?\d{1,4})\b\s*[:.\-]?\s*(.*?)(?=(?:\n\s*(?:HN\d{2,4}|CA[- ]?\d{1,4})\b)|$)",
    re.IGNORECASE | re.DOTALL,
)
_CHILD_RE = re.compile(
    r"===\s*CHILD\s+([A-Z0-9][A-Z0-9._-]*)\s*(?:\([^)]*\))?\s*===\s*(.*?)(?====\s|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_EPC_KEY_RE = re.compile(r"^EPC-\d+$", re.IGNORECASE)


@dataclass
class HistoriaNegocio:
    key: str
    text: str
    updates: str | None = None
    is_report: bool = False
    is_test_content: bool = False
    is_negative: bool = False
    is_communication: bool = False
    is_payment: bool = False
    is_transactional: bool = False
    superseded: bool = False
    devices: list[DeviceTarget] = field(default_factory=list)


def _normalize_hn_markers(blob: str) -> str:
    """Keep HN tokens findable when Confluence/Jira tables glue 'ID' + 'HN001'."""
    text = blob or ""
    text = re.sub(r"\.\s+(HN\d{2,4}\b)", r".\n\1", text, flags=re.IGNORECASE)
    text = re.sub(r"(?i)(?<![A-Z0-9])ID\s*(HN\d{2,4}\b)", r"\n\1", text)
    text = re.sub(r"(?i)\|\s*(HN\d{2,4}\b)", r"\n\1", text)
    return text


def parse_historias(blob: str) -> list[HistoriaNegocio]:
    text = _normalize_hn_markers(blob)
    found: list[HistoriaNegocio] = []
    seen: set[str] = set()
    for match in _HN_RE.finditer(text):
        key = match.group(1).upper()
        body = _keep_hn_structure(match.group(2))
        if key in seen:
            continue
        seen.add(key)
        found.append(_classify_hn(key, body))
    for match in _CA_RE.finditer(text):
        key = re.sub(r"\s+", "", match.group(1).upper())
        body = _keep_hn_structure(match.group(2))
        if key in seen:
            continue
        seen.add(key)
        found.append(_classify_hn(key, body))
    has_real_hn = bool(found)
    if not has_real_hn:
        for match in _CHILD_RE.finditer(text):
            child_key = match.group(1).upper()
            if _EPC_KEY_RE.match(child_key):
                continue
            body = _keep_hn_structure(match.group(2))
            hn_in_child = _HN_RE.search(body) or re.search(r"\bHN\d{2,4}\b", body, re.IGNORECASE)
            if hn_in_child:
                continue
            if child_key in seen:
                continue
            seen.add(child_key)
            found.append(_classify_hn(child_key, body))
    return _apply_modifiers(found)


def _keep_hn_structure(raw: str) -> str:
    """Keep HN line breaks for title/CA parsing. Do not flatten the whole body."""
    text = (raw or "").replace("\r\n", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def hn_title(text: str) -> str:
    """Visible HN name: text before user-story / CA boilerplate."""
    chunk = _keep_hn_structure(text)
    chunk = re.split(
        r"\bHistoria de negocio\b|\bHistoria de usuario\b|\bCriterios de aceptaci[oó]n\b|\bYo como\b",
        chunk,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    chunk = re.sub(r"^[-–—:\s]+", "", chunk)
    first = chunk.split("\n", 1)[0]
    return normalize_blob(first)[:200]


def _classify_hn(key: str, body: str) -> HistoriaNegocio:
    lowered = body.lower()
    title = hn_title(body).lower()
    updates = None
    update_match = re.search(r"actualiza(?:r)?(?:\s+la)?\s+(hn\d{2,4})", lowered)
    if update_match:
        updates = update_match.group(1).upper()
    is_report = bool(re.search(r"\breportes?\b|\bm[eé]tricas?\b|\bbusiness intelligence\b", title))
    is_transactional = any(
        token in title
        for token in (
            "flujo transaccional",
            "flujo de contratación",
            "contratación norte-sur",
            "iniciar el flujo",
            "medios de pago",
            "medio de pago",
            "adquisic",
        )
    )
    return HistoriaNegocio(
        key=key,
        text=body,
        updates=updates,
        is_report=is_report,
        is_test_content=any(token in lowered for token in (
            "contenido para", "datos de prueba", "compartir contenido", "contenido de prueba",
        )),
        is_negative=any(token in lowered for token in (
            "no liberar", "no publicar", "no habilitar", "no se encuentre publicado",
        )),
        is_communication="comunicaci" in lowered,
        is_payment=any(token in title for token in ("medio de pago", "medios de pago")),
        is_transactional=is_transactional,
        devices=extract_devices_from_text(body, source=key),
    )


def _apply_modifiers(items: list[HistoriaNegocio]) -> list[HistoriaNegocio]:
    by_key = {item.key: item for item in items}
    for item in items:
        if item.updates and item.updates in by_key:
            by_key[item.updates].superseded = True
    return items


def text_without_historias(blob: str) -> str:
    """BRF-level prose with HN bodies removed so HN devices are not applied globally."""
    text = _normalize_hn_markers(blob)
    return _HN_RE.sub("\n", text)


def functional_historias(items: list[HistoriaNegocio]) -> list[HistoriaNegocio]:
    return [
        item
        for item in items
        if not item.superseded and not item.is_report and not item.is_test_content
    ]
