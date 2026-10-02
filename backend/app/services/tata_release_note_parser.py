"""Header-aware Tata Release Note parser.

Does not share heading classifiers or ticket regexes with the DAMCO walker.
QCO stays qco[]. INCIDENT stays incidents[]. TBRF is never an Epic.
"""

from __future__ import annotations

import io
import re
from typing import Any

import pdfplumber

from app.services.rn_normalized import NORMALIZED_BUCKETS, NormalizedRnScope, RnItem

_TATA_KEY_RE = re.compile(r"\b([A-Z]{3,10})-\s*(\d{2,6})\b")
_TBRF_PROJECTS = {"TBRF", "TBRFRE", "BRFRE", "BRF"}
_FALSE_PROJECTS = {"THE", "AND", "FOR", "FIX", "APK", "PDF", "HTTP", "HTTPS", "UAT"}
_EPIC_HEADER = re.compile(r"EPIC\s*IDS?|TECHNICAL\s+EPIC", re.IGNORECASE)
_BRF_HEADER = re.compile(r"TBRF|TECHNICAL\s+BRF|\bBRF\b", re.IGNORECASE)
_INCIDENT_HEADER = re.compile(r"INCIDENT(?:E|\s*ID)?", re.IGNORECASE)
_BUG_ID_HEADER = re.compile(r"BUG\s*ID|ISSUE\s*ID", re.IGNORECASE)

_HEADING_BUCKETS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"KNOWN\s+ISSUES?", re.IGNORECASE), "known_issues"),
    (re.compile(r"QA\s+REPORTS?", re.IGNORECASE), "qa_evidence"),
    (re.compile(r"FEATURES?\s+IN\s+SCOPE", re.IGNORECASE), "technical_epics"),
    (re.compile(r"\bQCO\b", re.IGNORECASE), "qco"),
    (re.compile(r"\bNCO\b", re.IGNORECASE), "nco"),
    (re.compile(r"QC\s*BUGS?", re.IGNORECASE), "qc_bugs"),
    (re.compile(r"QA\s*BUGS?", re.IGNORECASE), "qa_bugs"),
    (re.compile(r"\bTRI\b", re.IGNORECASE), "tri"),
    (re.compile(r"ISSUES\s+ADDRESSED", re.IGNORECASE), "incidents"),
    (re.compile(r"\bINCIDENT(?:E|S|\s+ID)?\b", re.IGNORECASE), "incidents"),
    (re.compile(r"TECHNICAL\s+EPIC|EPIC\s*IDS?", re.IGNORECASE), "technical_epics"),
]


def _norm_cell(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\n", " ")).strip()


def extract_tata_keys(text: str) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for project, number in _TATA_KEY_RE.findall(text or ""):
        project_u = project.upper()
        if project_u in _FALSE_PROJECTS:
            continue
        key = f"{project_u}-{number}"
        if key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def classify_tata_heading(label: str) -> str | None:
    text = _norm_cell(label)
    if len(text) > 140:
        return None
    for pattern, bucket in _HEADING_BUCKETS:
        if pattern.search(text):
            return bucket
    return None


def classify_tata_table_headers(header_row: list[str | None], current: str | None) -> str | None:
    joined = " ".join(_norm_cell(cell) for cell in header_row)
    upper = joined.upper()
    if not upper.strip():
        return None
    if "COUNTRY" in upper and ("FW" in upper or "DEBUG" in upper or "VERSION" in upper):
        return "untracked"
    if "HARDWARE" in upper or (upper.startswith("BRAND") or " MODEL" in f" {upper}"):
        return "untracked"
    if "APK NAME" in upper or "GIT TAG" in upper or "BRANCH NAME" in upper:
        return "untracked"
    if "KNOWN" in upper:
        return "known_issues"
    if "TEST REPORT" in upper or "FEATURE TEST REPORT" in upper or "SANITY" in upper:
        return "qa_evidence"
    if _EPIC_HEADER.search(upper) or "TECHNICAL BRF" in upper:
        return "technical_epics"
    if current == "known_issues" and _INCIDENT_HEADER.search(upper):
        return "known_issues"
    if current == "qa_evidence" and _BUG_ID_HEADER.search(upper):
        return "qa_evidence"
    if _INCIDENT_HEADER.search(upper):
        return "incidents"
    if "ISSUE ID" in upper:
        return "incidents"
    if re.search(r"\bBUG ID\b", upper) and "SUMMARY" in upper:
        return "incidents"
    if re.search(r"\bBUG ID\b", upper) and current == "qa_evidence":
        return "qa_evidence"
    if re.search(r"\bQCO\b", upper):
        return "qco"
    if re.search(r"\bNCO\b", upper):
        return "nco"
    if "QC BUG" in upper:
        return "qc_bugs"
    if "QA BUG" in upper:
        return "qa_bugs"
    if re.search(r"\bTRI\b", upper):
        return "tri"
    return None


def _header_index(header_row: list[str | None], pattern: re.Pattern[str]) -> int | None:
    for index, cell in enumerate(header_row):
        if pattern.search(_norm_cell(cell)):
            return index
    return None


def _keys_from_cell(cell: str | None, next_cell: str | None = None) -> list[str]:
    text = _norm_cell(cell)
    keys = extract_tata_keys(text)
    dangling = re.search(r"\b([A-Z]{3,10})-\s*$", text)
    if dangling and next_cell:
        extra = re.match(r"\s*(\d{2,6})\b", _norm_cell(next_cell))
        if extra:
            key = f"{dangling.group(1).upper()}-{extra.group(1)}"
            if key not in keys:
                keys.append(key)
    return keys


def detect_tata_device(filename: str, text: str) -> tuple[str | None, str | None]:
    upper_name = (filename or "").upper()
    cover = (text or "")[:800].upper()
    blob = f"{upper_name}\n{cover}"
    if re.search(r"NON[_\s-]*ANDROIDTV[_\s-]*LG|NON-ANDROID TV[_ ]LG|\bLG_RELEASE", blob):
        return "STV Tata LG", "STV"
    if re.search(r"NON[_\s-]*ANDROIDTV[_\s-]*SAMSUNG|NON-ANDROID TV[_ ]SAMSUNG|SAMSUNG_RELEASE", blob):
        return "STV Tata Samsung", "STV"
    if re.search(r"HISENSE|HI[\s_]?SENSE", upper_name) or re.search(
        r"NON[_\s-]*ANDROIDTV[_\s-]*HI", blob
    ):
        return "STV Tata Hisense", "STV"
    if re.search(r"NON[_\s-]*ANDROID", blob):
        return None, "STV"
    if re.search(r"HBOMAX|_ADT_|ANDROIDTV|ANDROID\s*TV", blob) and "LAUNCHER" not in blob:
        return "STV Tata ADT", "STV"
    if "LAUNCHER" in blob or re.search(r"\bATS\b", blob):
        return "STB IPTV", "ATV Launcher"
    return None, None


def parse_tata_release_note(pdf_bytes: bytes, filename: str = "") -> NormalizedRnScope:
    scope = NormalizedRnScope(vendor="tata")
    seen: dict[str, set[str]] = {name: set() for name in NORMALIZED_BUCKETS}
    current: str | None = None
    sticky_header: list[str | None] = []

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            full_text_parts: list[str] = []
            for page_index, page in enumerate(pdf.pages, start=1):
                words = page.extract_words() or []
                lines: dict[int, list] = {}
                for word in words:
                    lines.setdefault(round(word["top"]), []).append(word)
                events: list[tuple[float, str, Any]] = []
                for top, line_words in lines.items():
                    line_words.sort(key=lambda item: item["x0"])
                    line_text = " ".join(item["text"] for item in line_words)
                    bucket = classify_tata_heading(line_text)
                    if bucket:
                        events.append((top, "heading", bucket))
                page_text = page.extract_text() or ""
                full_text_parts.append(page_text)
                for table in page.find_tables():
                    events.append((table.bbox[1], "table", table))
                events.sort(key=lambda item: item[0])

                toc_indices = _toc_indices(events)
                for idx, (_top, kind, payload) in enumerate(events):
                    if kind == "heading":
                        if idx not in toc_indices:
                            current = payload
                        continue
                    rows = payload.extract() or []
                    if not rows:
                        continue
                    header_row = list(rows[0])
                    override = classify_tata_table_headers(header_row, current)
                    if override == "untracked":
                        continue
                    continuation = _looks_like_continuation(header_row)
                    bucket = override or current
                    if bucket is None or bucket not in NORMALIZED_BUCKETS:
                        continue
                    if override and not continuation:
                        sticky_header = header_row
                        current = override
                    working_header = sticky_header if continuation else header_row
                    if not continuation:
                        sticky_header = header_row
                    _ingest_table(
                        scope,
                        seen,
                        rows,
                        working_header,
                        bucket,
                        current or "",
                        page_index,
                        skip_header=not continuation,
                    )
            joined = "\n".join(full_text_parts)
            device, family = detect_tata_device(filename, joined)
            scope.device = device
            scope.family = family
            version_match = re.search(r"\bv?(\d+\.\d+\.\d+)\b", filename) or re.search(
                r"\bv?(\d+\.\d+\.\d+)\b", joined[:1500]
            )
            if version_match:
                scope.version = version_match.group(1)
    except Exception:
        return scope
    return scope


def _looks_like_continuation(header_row: list[str | None]) -> bool:
    first = _norm_cell(header_row[0] if header_row else "")
    joined = " ".join(_norm_cell(cell) for cell in header_row)
    if classify_tata_table_headers(header_row, None):
        return False
    if first.isdigit() or first.startswith("["):
        return True
    if extract_tata_keys(joined) and not classify_tata_heading(joined):
        return True
    return not any(_norm_cell(cell) for cell in header_row)


def _toc_indices(events: list[tuple[float, str, Any]]) -> set[int]:
    toc: set[int] = set()
    run: list[int] = []
    last_top: float | None = None

    def flush() -> None:
        if len(run) >= 3:
            toc.update(run)
        run.clear()

    for index, (top, kind, _payload) in enumerate(events):
        if kind == "heading":
            if run and last_top is not None and top - last_top > 50:
                flush()
            run.append(index)
            last_top = top
        else:
            flush()
            last_top = None
    flush()
    return toc


def _ingest_table(
    scope: NormalizedRnScope,
    seen: dict[str, set[str]],
    rows: list[list[str | None]],
    header_row: list[str | None],
    bucket: str,
    section: str,
    page: int,
    skip_header: bool = True,
) -> None:
    header_names = [_norm_cell(cell) for cell in header_row]
    table_header = " | ".join(name for name in header_names if name)
    epic_idx = _header_index(header_row, _EPIC_HEADER)
    brf_idx = _header_index(header_row, _BRF_HEADER)
    incident_idx = _header_index(header_row, _INCIDENT_HEADER)
    bug_idx = _header_index(header_row, _BUG_ID_HEADER)
    start = 1 if skip_header and classify_tata_table_headers(header_row, bucket) else 0

    for row in rows[start:]:
        if not row:
            continue
        tbrf_id = None
        column = ""
        keys: list[str] = []
        if bucket == "technical_epics":
            if brf_idx is not None:
                brf_keys = _column_keys(row, brf_idx)
                tbrf_id = next((key for key in brf_keys if key.split("-")[0] in _TBRF_PROJECTS), None)
            if epic_idx is not None:
                keys = [key for key in _column_keys(row, epic_idx) if key.split("-")[0] not in _TBRF_PROJECTS]
                column = header_names[epic_idx] if epic_idx < len(header_names) else "EPIC ID"
            else:
                keys = [
                    key
                    for key in extract_tata_keys(" ".join(_norm_cell(cell) for cell in row))
                    if key.split("-")[0] not in _TBRF_PROJECTS
                ]
                column = "EPIC ID"
        elif bucket == "incidents":
            idx = incident_idx if incident_idx is not None else bug_idx
            if idx is not None:
                keys = _column_keys(row, idx)
                column = header_names[idx] if idx < len(header_names) else "INCIDENT ID"
            else:
                keys = extract_tata_keys(" ".join(_norm_cell(cell) for cell in row))
                column = "INCIDENT ID"
            keys = [key for key in keys if key.split("-")[0] not in _TBRF_PROJECTS]
        elif bucket == "qa_evidence":
            idx = bug_idx
            if idx is not None:
                keys = _column_keys(row, idx)
                column = header_names[idx] if idx < len(header_names) else "Bug ID"
            else:
                keys = extract_tata_keys(" ".join(_norm_cell(cell) for cell in row))
                column = "Bug ID"
        elif bucket == "known_issues":
            idx = incident_idx
            if idx is not None:
                keys = _column_keys(row, idx)
                column = header_names[idx] if idx < len(header_names) else "INCIDENT ID"
            else:
                keys = extract_tata_keys(" ".join(_norm_cell(cell) for cell in row))
                column = "Known Issue"
            keys = [key for key in keys if key.split("-")[0] not in _TBRF_PROJECTS]
        else:
            keys = [
                key
                for key in extract_tata_keys(" ".join(_norm_cell(cell) for cell in row))
                if not (bucket != "qco" and key.split("-")[0] in _TBRF_PROJECTS and bucket == "technical_epics")
            ]
            column = bucket

        title = " | ".join(_norm_cell(cell) for cell in row if _norm_cell(cell))
        for key in keys:
            if key in seen[bucket]:
                continue
            seen[bucket].add(key)
            getattr(scope, bucket).append(
                RnItem(
                    id=key,
                    title=title,
                    section=section,
                    table_header=table_header,
                    column=column,
                    tbrf_id=tbrf_id,
                    page=page,
                )
            )


def _column_keys(row: list[str | None], index: int) -> list[str]:
    cell = row[index] if index < len(row) else ""
    nxt = row[index + 1] if index + 1 < len(row) else ""
    keys = _keys_from_cell(cell, nxt)
    if not keys:
        keys = extract_tata_keys(_norm_cell(cell))
    return keys
