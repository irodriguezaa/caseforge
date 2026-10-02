"""Classify a Release Note PDF as DAMCO or TATA.

Default is DAMCO so an ambiguous document never enters the Tata walker.
"""

from __future__ import annotations

import io
import re
from typing import Literal

from pypdf import PdfReader

RnVendor = Literal["damco", "tata"]

_DAMCO_NAME = re.compile(r"DAMCO", re.IGNORECASE)
_TATA_NAME = re.compile(
    r"ATSTATA|\bTATA\b|AMX_UNMANAGED|AMX ATV LAUNCHER|DEBITCARDS|"
    r"tata_stv|tata_launcher|HBOMAX",
    re.IGNORECASE,
)
_DAMCO_BODY = re.compile(
    r"QCO'?s?\s*&\s*QA|Funcionalidad incluida|Incidencias productivas",
    re.IGNORECASE,
)
_TATA_BODY = re.compile(
    r"Issues Addressed by TATA|QA Reports from TATA|Technical BRF ID|"
    r"INCIDENT ID|\bINCIDENTE\b|Features In Scope|AMX ATV Launcher|"
    r"ATSTata",
    re.IGNORECASE,
)


def _sample_text(pdf_bytes: bytes, max_pages: int = 2) -> str:
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        parts: list[str] = []
        for page in reader.pages[:max_pages]:
            text = page.extract_text() or ""
            if text:
                parts.append(text)
        return "\n".join(parts)
    except Exception:
        return ""


def detect_rn_vendor(
    filename: str = "",
    pdf_bytes: bytes | None = None,
    text: str | None = None,
) -> RnVendor:
    name = filename or ""
    if _DAMCO_NAME.search(name):
        return "damco"
    if _TATA_NAME.search(name):
        return "tata"
    body = text if text is not None else (_sample_text(pdf_bytes) if pdf_bytes else "")
    if _DAMCO_BODY.search(body):
        return "damco"
    if _TATA_BODY.search(body):
        return "tata"
    return "damco"
