"""Minimal BE Release Note header extraction.

The RN is an optional source of Entregable / Nombre / SWF. This is not the Apps analyzer
and not the Operativas analyzer: no feature counts, devices, EPCs, or TRI tables.
If evidence is not clear, fields stay None — never invented from the filename.
"""

import io
import re
from dataclasses import dataclass

import pdfplumber

_SWF_CANONICAL = {"neoris": "Neoris", "tata": "Tata", "hitss": "Hitss"}
_SWF_RE = re.compile(r"\b(Neoris|Tata|Hitss)\b", re.IGNORECASE)
_ENTREGABLE_RE = re.compile(r"^Entregable\s*[:\-]\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_NOMBRE_RE = re.compile(r"^Nombre\s*[:\-]\s*(.+)$", re.IGNORECASE | re.MULTILINE)


@dataclass(frozen=True)
class BeRnHeader:
    entregable: str | None
    name: str | None
    swf: str | None


def _page_one_text(pdf_bytes: bytes) -> str:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        if not pdf.pages:
            return ""
        return pdf.pages[0].extract_text() or ""


def extract_be_rn_header(pdf_bytes: bytes) -> BeRnHeader:
    """Page-1 evidence only. Ambiguous or missing values stay None."""
    text = _page_one_text(pdf_bytes)

    entregable_match = _ENTREGABLE_RE.search(text)
    name_match = _NOMBRE_RE.search(text)
    swf_hits = {_SWF_CANONICAL[m.group(1).lower()] for m in _SWF_RE.finditer(text)}
    swf = next(iter(swf_hits)) if len(swf_hits) == 1 else None

    entregable = entregable_match.group(1).strip() if entregable_match else None
    name = name_match.group(1).strip() if name_match else None
    return BeRnHeader(
        entregable=entregable or None,
        name=name or None,
        swf=swf,
    )
