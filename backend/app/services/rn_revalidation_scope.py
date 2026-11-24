"""View of a revalidation RN: what is new versus the origin.

The stored analysis stays complete. Case generation keeps using that full note,
so a key whose text changed still produces its delta. This module only builds
the alcance that the screen shows, and it can append a QA row that the table
reader left outside the grid.
"""

from __future__ import annotations

import io
import re
from typing import Any

from pypdf import PdfReader

_BUCKETS = (
    "technical_epics",
    "nco",
    "qco",
    "qa_bugs",
    "qc_bugs",
    "tri",
    "incidents",
    "known_issues",
    "qa_evidence",
    "qa_qc",
)


def origin_scope_keys(raw_analysis: dict[str, Any] | None) -> set[str]:
    if not isinstance(raw_analysis, dict):
        return set()
    normalized = raw_analysis.get("normalized")
    if not isinstance(normalized, dict):
        return set()
    keys: set[str] = set()
    for bucket in _BUCKETS:
        rows = normalized.get(bucket)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            key = str(row.get("id") or row.get("key") or "").strip().upper()
            if key:
                keys.add(key)
    return keys


def narrow_revalidation_analysis(
    analysis: dict[str, Any],
    origin_raw: dict[str, Any] | None,
) -> dict[str, Any]:
    """Drop issues the origin RN already listed. Counts follow what remains."""
    prior = origin_scope_keys(origin_raw)
    raw = analysis.get("raw_analysis")
    if not prior or not isinstance(raw, dict):
        return analysis
    normalized = raw.get("normalized")
    if not isinstance(normalized, dict):
        return analysis
    removed = 0
    for bucket in _BUCKETS:
        rows = normalized.get(bucket)
        if not isinstance(rows, list):
            continue
        kept: list[Any] = []
        for row in rows:
            if not isinstance(row, dict):
                kept.append(row)
                continue
            key = str(row.get("id") or row.get("key") or "").strip().upper()
            if key and key in prior:
                removed += 1
                continue
            kept.append(row)
        normalized[bucket] = kept
    if removed == 0:
        return analysis
    analysis["features_count"] = len(normalized.get("technical_epics") or [])
    analysis["nco_issues_count"] = len(normalized.get("nco") or [])
    analysis["tri_issues_count"] = len(normalized.get("tri") or [])
    analysis["qa_qc_issues_count"] = (
        len(normalized.get("qa_qc") or [])
        + len(normalized.get("qa_bugs") or [])
        + len(normalized.get("qc_bugs") or [])
    )
    note = (
        "Revalidación: el alcance queda solo en lo que no venía en la versión origen. "
        f"{removed} issue(s) ya conocidos quedaron fuera."
    )
    observations = list(analysis.get("observations") or [])
    if note not in observations:
        observations.append(note)
    analysis["observations"] = observations
    return analysis


_LOOSE_QA_LINE_RE = re.compile(
    r"^(?:QA|QC)\s+((?!BRF)[A-Z][A-Z0-9]{1,7}-\d{2,6})\b",
    re.IGNORECASE,
)


def loose_qa_key(line: str) -> tuple[str, str] | None:
    """A line that is itself a QA/QC ticket. A mention inside a sentence is not."""
    plain = re.sub(r"^[^A-Za-z0-9]+", "", (line or "").strip())
    match = _LOOSE_QA_LINE_RE.match(plain)
    if not match:
        return None
    return match.group(1).upper(), plain


_TEXT_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")


def _pdf_text(pdf_bytes: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception:
        return ""
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _snippet(text: str, key: str) -> str:
    match = re.search(rf"\b{re.escape(key)}\b[^\n]{{0,180}}", text)
    if not match:
        return key
    line = re.sub(r"\s+", " ", match.group(0)).strip()
    return line or key


def append_pdf_delta_keys(
    analysis: dict[str, Any],
    new_pdf: bytes | None,
    origin_pdf: bytes | None,
) -> dict[str, Any]:
    """Add keys that exist only in the new PDF. Does not remove stored rows."""
    if not new_pdf or not origin_pdf:
        return analysis
    raw = analysis.get("raw_analysis")
    if not isinstance(raw, dict):
        return analysis
    normalized = raw.get("normalized")
    if not isinstance(normalized, dict):
        return analysis
    new_text = _pdf_text(new_pdf)
    fresh = set(_TEXT_KEY_RE.findall(new_text)) - set(_TEXT_KEY_RE.findall(_pdf_text(origin_pdf)))
    present = origin_scope_keys(raw)
    qa = list(normalized.get("qa_qc") or [])
    added = 0
    for key in sorted(fresh):
        if key in present:
            continue
        qa.append({"id": key, "title": _snippet(new_text, key)})
        present.add(key)
        added += 1
    if added == 0:
        return analysis
    normalized["qa_qc"] = qa
    analysis["qa_qc_issues_count"] = int(analysis.get("qa_qc_issues_count") or 0) + added
    return analysis
