"""TRI/QCO as a distinct RN source. Never copy VPN/credentials into candidates."""

from __future__ import annotations

import re
from dataclasses import dataclass

import pdfplumber
import io

from app.services.operativa_engine.devices import DeviceTarget, extract_devices_from_text, normalize_blob

_TRI_RE = re.compile(r"\b((?:TRI|QCO)-\d+)\b", re.IGNORECASE)


@dataclass(frozen=True)
class TriIssue:
    key: str
    summary: str
    devices: list[DeviceTarget]


def extract_tris(pdf_bytes: bytes | None) -> list[TriIssue]:
    if not pdf_bytes:
        return []
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            text = "\n".join((page.extract_text() or "") for page in pdf.pages)
    except Exception:
        return []
    lowered = text.lower()
    if "vpn" in lowered or "pre shared" in lowered:
        # Keep parsing TRI keys but never return credential lines.
        pass
    found: dict[str, TriIssue] = {}
    for match in _TRI_RE.finditer(text):
        key = match.group(1).upper()
        start = max(0, match.start() - 80)
        end = min(len(text), match.end() + 240)
        window = normalize_blob(text[start:end])
        if any(token in window.lower() for token in ("password", "pre shared", "token", "usuario vpn")):
            window = normalize_blob(text[match.start(): min(len(text), match.end() + 160)])
        devices = extract_devices_from_text(window, source=f"{key} RN")
        found[key] = TriIssue(key=key, summary=window[:280], devices=devices)
    return list(found.values())


