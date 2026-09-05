"""Release Note Operativo extraction service.

Structurally different document family from the device-based Release RNs (WEB/iOS/tvOS/etc.)
handled by release_note_analyzer.py -- zero code reuse from there, this is a fresh analyzer for
a fresh table convention (BRF | EPC | Tipo | Alcance | Nota RTE, plus a second "BRFs en el
Scope" table and a TRI/"Incidentes productivos" table, none of which exist in the device-RN
family).

This module extracts (1) RN header fields for Paso 2 (entregable / name / cluster) and
(2) EPCs + qc_suggestion for Paso 4. Paso 3 fields (alcance funcional, dispositivos, dates,
Jira filter, instrucciones) are never inferred here -- the user fills them via the router.

Logical rows are rebuilt before becoming EPC records: repeated page headers, cover blobs,
and page-break continuations are not independent BRF/EPC rows. The EPC-source table is the
Incluir-en-QC source; "BRFs en el Scope" only adds a BRF that never appeared there.
"""

import io
import re

import pdfplumber

# Table 1's header: "Brief Key | Clave | Tipo de Epica | Alcance | Nota RTE | Versiones..."
# This is the RN's own primary scope declaration (EPCs already in "Épicas Finalizadas").
_EPC_TABLE_HEADER_MARKERS = ("BRIEF KEY", "TIPO DE EPICA")

# Table 2's header: "Clave | Tipo de BRF | Estado | Alcance | Nota RTE | Versiones..."
_BRF_TABLE_HEADER_MARKERS = ("TIPO DE BRF", "ESTADO")

# The "Incidentes productivos" / TRI table -- explicitly NOT an EPC Operativo.
_TRI_TABLE_HEADER_MARKERS = ("TIPO DE INCIDENCIA",)

# VPN/credentials (and similar) stop tracking entirely -- never treated as EPC data.
_STOP_HEADER_MARKERS = ("REGIÓN", "SERVER")

_BRF_KEY_RE = re.compile(r"\bBRF-\d+\b", re.IGNORECASE)
_LEADING_BRF_RE = re.compile(r"^\s*(BRF-\d+)\b", re.IGNORECASE)
_LEADING_EPC_RE = re.compile(r"^\s*(EPC-(\d+))", re.IGNORECASE)
_WRAP_DIGITS_COLON_RE = re.compile(r"^(\d{1,4}):\s*(.*)$", re.DOTALL)
_STATUS_BADGES = ["In Validate", "In Develop", "In Progress", "Done", "To Do", "Cancelled", "Cancelado"]
_STATUS_RE = re.compile(r"(" + "|".join(re.escape(s) for s in _STATUS_BADGES) + r")\s*$", re.IGNORECASE)
_COVER_LABEL_RE = re.compile(
    r"\b(fecha de prod|matriz de validaci[oó]n|integrador|\bpm\b|\bbo\b)\b",
    re.IGNORECASE,
)

# Generic Spanish phrasing for an explicit exclusion signal in Nota RTE.
#
# Regression: "no se prueba" was tried and REMOVED -- it false-matched the real BRF-17702 note
# ("Cambio en PROD, no se prueba en UAT"), which is purely informational about WHERE testing
# happens (UAT vs PROD), not whether QC applies at all.
_EXCLUSION_PHRASES = (
    "no requiere validaci",
    "fuera de scope",
    "fuera del scope",
    "sin validaci",
)
_NO_QC_TESTS_RE = re.compile(
    r"no\s+requiere(?:\s+de)?\s+pruebas?(?:\s+de)?\s+qc",
    re.IGNORECASE,
)
# PIN/pincode lot generation in title/description -- not an incidental "PIN" mention.
_PIN_TOKEN = r"(?:pincodes?|pin[\s\-]*codes?|pin(?:es|s)?)"
_PIN_GENERATION_RE = re.compile(
    rf"(?:generar|generacion)\s+(?:de\s+)?(?:(?:los|el|la)\s+)?(?:lotes?\s+(?:de\s+)?)?{_PIN_TOKEN}\b"
    rf"|lotes?\s+de\s+{_PIN_TOKEN}\b",
    re.IGNORECASE,
)

_OPE_CODE_RE = re.compile(r"\b(OPE-[A-Z]+-\d{4}-[A-Z]+)\b", re.IGNORECASE)
_VERSION_LINE_RE = re.compile(r"Versi[oó]n\s+(OPE-[A-Z]+-\d{4}-[A-Z]+)", re.IGNORECASE)
_TITLE_LINE_RE = re.compile(
    r"^(OPE-[A-Z]+-\d{4}-[A-Z]+)\s+Release\s+notes\s*$", re.IGNORECASE | re.MULTILINE
)
_ENTREGABLE_LABEL_RE = re.compile(r"^Entregable\s*[:\-]\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_RELEASE_PRODUCT_HEADING_RE = re.compile(
    r"^Release\s+(?!notes?\b)(.{3,80})$", re.IGNORECASE | re.MULTILINE
)
_CLUSTER_FROM_OPE_SUFFIX = {
    "AUP": "AUP",
    "ANDINA": "Andina",
    "AND": "Andina",
    "CENAM": "CENAM",
    "DOMINICANA": "Dominicana",
    "GLOBAL": "Global",
}


class RnHeader:
    """Cover-page identity. Any field may be None when the RN has no clear evidence."""

    __slots__ = ("entregable", "name", "cluster")

    def __init__(self, entregable: str | None, name: str | None, cluster: str | None) -> None:
        self.entregable = entregable
        self.name = name
        self.cluster = cluster


def extract_rn_header(pdf_bytes: bytes) -> RnHeader:
    """Reads page 1 only. Returns None for a field rather than guessing from the filename
    or from EPC ticket titles (those mention countries/clusters that are not the RN's own)."""
    page1 = _extract_page1_text(pdf_bytes)
    name = _extract_name(page1)
    cluster = _cluster_from_ope_code(name)
    entregable = _extract_entregable(page1)
    return RnHeader(entregable=entregable, name=name, cluster=cluster)


def _extract_page1_text(pdf_bytes: bytes) -> str:
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            if not pdf.pages:
                return ""
            return pdf.pages[0].extract_text() or ""
    except Exception:
        return ""


def _extract_name(page1: str) -> str | None:
    version_match = _VERSION_LINE_RE.search(page1)
    if version_match:
        return version_match.group(1).upper()
    title_match = _TITLE_LINE_RE.search(page1)
    if title_match:
        return title_match.group(1).upper()
    code_match = _OPE_CODE_RE.search(page1)
    if code_match:
        return code_match.group(1).upper()
    return None


def _cluster_from_ope_code(name: str | None) -> str | None:
    if not name:
        return None
    suffix = name.rsplit("-", 1)[-1].upper()
    return _CLUSTER_FROM_OPE_SUFFIX.get(suffix)


def _extract_entregable(page1: str) -> str | None:
    labeled = _ENTREGABLE_LABEL_RE.search(page1)
    if labeled:
        candidate = re.sub(r"\s+", " ", labeled.group(1)).strip()
        if candidate:
            return candidate
    heading = _RELEASE_PRODUCT_HEADING_RE.search(page1)
    if heading:
        line = re.sub(r"\s+", " ", heading.group(0)).strip()
        if line and "http" not in line.lower():
            return line
    return None


class EpcCandidate:
    __slots__ = ("brf_key", "epc_key", "titulo", "alcance", "nota_rte", "estado_jira", "qc_suggestion")

    def __init__(
        self,
        brf_key: str,
        epc_key: str | None,
        titulo: str,
        alcance: str | None,
        nota_rte: str | None,
        estado_jira: str | None,
    ) -> None:
        self.brf_key = brf_key
        self.epc_key = epc_key
        self.titulo = titulo
        self.alcance = alcance
        self.nota_rte = nota_rte
        self.estado_jira = estado_jira
        self.refresh_suggestion()

    def refresh_suggestion(self) -> None:
        self.qc_suggestion = _compute_suggestion(
            nota_rte=self.nota_rte,
            estado_jira=self.estado_jira,
            titulo=self.titulo,
            alcance=self.alcance,
        )


def _fold_suggestion_text(value: str | None) -> str:
    text = re.sub(r"\s+", " ", (value or "").lower())
    return (
        text.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ü", "u")
    )


def _nota_rte_excludes_qc(nota_rte: str | None) -> bool:
    lowered = _fold_suggestion_text(nota_rte)
    if not lowered:
        return False
    if any(phrase in lowered for phrase in _EXCLUSION_PHRASES):
        return True
    return bool(_NO_QC_TESTS_RE.search(lowered))


def _is_pin_lot_generation(*parts: str | None) -> bool:
    blob = _fold_suggestion_text(" ".join(part for part in parts if part))
    if not blob:
        return False
    return bool(_PIN_GENERATION_RE.search(blob))


def _compute_suggestion(
    nota_rte: str | None,
    estado_jira: str | None,
    titulo: str | None = None,
    alcance: str | None = None,
) -> str:
    """A SUGGESTION only -- the router/UI must always let the user override include_in_qc."""
    if _nota_rte_excludes_qc(nota_rte) or _is_pin_lot_generation(titulo, alcance):
        return "SUGERIDO_EXCLUIR"

    if estado_jira and estado_jira.strip().lower() in ("in validate", "done"):
        return "SUGERIDO_INCLUIR"

    return "REQUIERE_REVISION"


def _extract_status(cell_text: str) -> tuple[str, str | None]:
    """Splits a status badge from cell text, including when leftover columns were joined after it."""
    text = cell_text.strip()
    if not text:
        return "", None
    matches = list(re.finditer("|".join(re.escape(s) for s in _STATUS_BADGES), text, re.IGNORECASE))
    if not matches:
        return text, None
    match = matches[-1]
    tail = text[match.end() :].strip()
    if tail and len(tail) > 24 and not re.match(r"^(QC|OPE-|P[aá]gina|-?\d{4})", tail, re.IGNORECASE):
        return text, None
    return text[: match.start()].strip(), match.group(0)


def _nonempty_cells(row: list[str | None]) -> list[str]:
    return [(cell or "").strip() for cell in row if (cell or "").strip()]


def _header_kind_from_joined(joined: str) -> str | None:
    upper = joined.upper()
    if any(marker in upper for marker in _STOP_HEADER_MARKERS):
        return "stop"
    if all(marker in upper for marker in _BRF_TABLE_HEADER_MARKERS):
        return "brf_table"
    if all(marker in upper for marker in _EPC_TABLE_HEADER_MARKERS) or (
        "BRIEF KEY" in upper and "CLAVE" in upper
    ):
        return "epc_table"
    if any(marker in upper for marker in _TRI_TABLE_HEADER_MARKERS):
        return "tri_table"
    return None


def _looks_like_column_header(row: list[str | None]) -> bool:
    """Real column titles, not a cover/prose blob that happens to mention those words."""
    cells = _nonempty_cells(row)
    if len(cells) < 3:
        return False
    short = sum(1 for cell in cells if len(cell) <= 48)
    if short < 3:
        return False
    return _header_kind_from_joined(" ".join(cells)) is not None


def _classify_header(header_row: list[str | None]) -> str | None:
    if not _looks_like_column_header(header_row):
        return None
    return _header_kind_from_joined(" ".join(_nonempty_cells(header_row)))


def _find_header(rows: list[list[str | None]]) -> tuple[int | None, str | None]:
    for index, row in enumerate(rows[:8]):
        kind = _classify_header(row)
        if kind:
            return index, kind
    return None, None


def _looks_like_cover_kv_table(rows: list[list[str | None]]) -> bool:
    if not rows or max(len(row) for row in rows) > 3:
        return False
    blob = " ".join((cell or "") for row in rows[:6] for cell in row)
    return len(_COVER_LABEL_RE.findall(blob)) >= 2


def _clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("|", " ")).strip()


def _join_fragments(current: str, incoming: str) -> str:
    incoming = _clean_text(incoming)
    if not incoming:
        return current
    if not current:
        return incoming
    if incoming.lower() in current.lower():
        return current
    return f"{current} {incoming}".strip()


def _leading_brf(cell: str | None) -> str | None:
    match = _LEADING_BRF_RE.match(cell or "")
    return match.group(1).upper() if match else None


def parse_epc_identity_cell(cell: str | None) -> tuple[str | None, str]:
    """EPC key from the start of a cell. Glues digits wrapped onto the next line before `:`."""
    text = cell or ""
    match = _LEADING_EPC_RE.match(text)
    if not match:
        return None, _clean_text(text)
    digits = match.group(2)
    rest = text[match.end() :]
    wrapped = None
    newline_wrap = re.match(r"^[\s:]*\n[\s]*(\d{1,4}):\s*(.*)$", rest, re.DOTALL)
    if newline_wrap:
        wrapped = newline_wrap
    else:
        stripped = rest.lstrip(" \t")
        inline = _WRAP_DIGITS_COLON_RE.match(stripped)
        if inline and re.match(r"^[\s]*\d{1,4}:", rest):
            wrapped = inline
    if wrapped:
        digits = f"{digits}{wrapped.group(1)}"
        rest = wrapped.group(2) or ""
    else:
        rest = rest.lstrip(" :.\n")
    return f"EPC-{digits}", _clean_text(rest)


def stitch_wrapped_epc_key(current_key: str | None, fragment: str) -> tuple[str | None, str]:
    """Continue an EPC key split across a page/row (`EPC-2203` + `0: title`)."""
    blob = _clean_text(fragment)
    if not current_key or not blob:
        return current_key, blob
    wrapped = _WRAP_DIGITS_COLON_RE.match(blob)
    prefix = re.match(r"^EPC-(\d+)$", current_key, re.IGNORECASE)
    if wrapped and prefix:
        return f"EPC-{prefix.group(1)}{wrapped.group(1)}", _clean_text(wrapped.group(2) or "")
    return current_key, blob


def _row_identity(row: list[str | None]) -> tuple[int | None, str | None, str | None, str]:
    """Identity cells must start with BRF- or EPC-. Mid-prose mentions are ignored."""
    brf_idx = next((index for index, cell in enumerate(row) if _leading_brf(cell)), None)
    if brf_idx is None:
        epc_idx = next((index for index, cell in enumerate(row) if parse_epc_identity_cell(cell)[0]), None)
        if epc_idx is None:
            return None, None, None, ""
        epc_key, title = parse_epc_identity_cell(row[epc_idx])
        nearby_brf = next((_leading_brf(cell) for cell in row if _leading_brf(cell)), None)
        return epc_idx, nearby_brf, epc_key, title

    brf_key = _leading_brf(row[brf_idx])
    same_cell_epc, same_rest = parse_epc_identity_cell(row[brf_idx])
    if same_cell_epc:
        return brf_idx, brf_key, same_cell_epc, same_rest

    next_cell = row[brf_idx + 1] if len(row) > brf_idx + 1 else ""
    epc_key, title = parse_epc_identity_cell(next_cell)
    if not epc_key:
        title = ""
    brf_match = _LEADING_BRF_RE.match(row[brf_idx] or "")
    brf_rest = (row[brf_idx] or "")[brf_match.end() :].lstrip(": ") if brf_match else ""
    if brf_rest and not title:
        title = _clean_text(brf_rest)
    return brf_idx, brf_key, epc_key, title


def _row_fields(
    row: list[str | None], identity_idx: int, title_from_clave: str
) -> tuple[str, str | None, str | None, str | None]:
    alcance_raw = (row[identity_idx + 3] or "").strip() if len(row) > identity_idx + 3 else ""
    nota_raw = (row[identity_idx + 4] or "").strip() if len(row) > identity_idx + 4 else ""
    estado_col = (row[identity_idx + 2] or "").strip() if len(row) > identity_idx + 2 else ""
    title, estado_badge = _extract_status(title_from_clave)
    estado = None
    estado_match = _STATUS_RE.search(estado_col) if estado_col else None
    if estado_match:
        estado = estado_match.group(1)
    estado = estado or estado_badge
    return (
        _clean_text(title),
        _clean_text(alcance_raw) or None,
        _clean_text(nota_raw) or None,
        estado,
    )


def _merge_into_draft(draft: EpcCandidate, row: list[str | None]) -> None:
    blob = _clean_text(" ".join(cell or "" for cell in row))
    if not blob:
        return
    identity_idx, _brf_key, epc_key, title_raw = _row_identity(row)
    if epc_key and draft.epc_key and epc_key.startswith(draft.epc_key) and len(epc_key) > len(draft.epc_key):
        draft.epc_key = epc_key
    stitched, leftover = stitch_wrapped_epc_key(draft.epc_key, blob)
    if stitched != draft.epc_key:
        draft.epc_key = stitched
        blob = leftover
        title_raw = leftover
    title, estado = _extract_status(title_raw or blob)
    alcance = None
    nota = None
    if identity_idx is not None and _leading_brf(row[identity_idx] if identity_idx < len(row) else ""):
        title, alcance, nota, estado = _row_fields(row, identity_idx, title_raw or blob)
    draft.titulo = _join_fragments(draft.titulo, title)
    if alcance and not draft.alcance:
        draft.alcance = alcance
    if nota and not draft.nota_rte:
        draft.nota_rte = nota
    combined, combined_estado = _extract_status(draft.titulo)
    if combined_estado:
        draft.titulo = combined
        estado = estado or combined_estado
    if estado and not draft.estado_jira:
        draft.estado_jira = estado
    draft.refresh_suggestion()


def _new_epc_draft(row: list[str | None]) -> EpcCandidate | None:
    identity_idx, brf_key, epc_key, title_raw = _row_identity(row)
    if identity_idx is None or not brf_key:
        return None
    title, alcance, nota, estado = _row_fields(row, identity_idx, title_raw)
    return EpcCandidate(brf_key, epc_key, title, alcance, nota, estado)


def _new_brf_scope_draft(row: list[str | None]) -> EpcCandidate | None:
    identity_idx, brf_key, epc_key, title_raw = _row_identity(row)
    if identity_idx is None or not brf_key:
        return None
    col0 = row[identity_idx] or ""
    match = _LEADING_BRF_RE.match(col0)
    rest = col0[match.end() :].lstrip(": ") if match else title_raw
    titulo, estado_from_badge = _extract_status(_clean_text(rest or title_raw))
    estado_col = (row[identity_idx + 2] or "").strip() if len(row) > identity_idx + 2 else ""
    estado = estado_col or estado_from_badge
    alcance = _clean_text(row[identity_idx + 3] or "") or None if len(row) > identity_idx + 3 else None
    nota_rte = _clean_text(row[identity_idx + 4] or "") or None if len(row) > identity_idx + 4 else None
    return EpcCandidate(brf_key, epc_key, titulo, alcance, nota_rte, estado)


def _enrich_from_scope(existing: EpcCandidate, incoming: EpcCandidate) -> None:
    """Scope table fills gaps; it must not replace EPC identity or invent a second row."""
    if not existing.estado_jira and incoming.estado_jira:
        existing.estado_jira = incoming.estado_jira
    if not existing.nota_rte and incoming.nota_rte:
        existing.nota_rte = incoming.nota_rte
    if not existing.titulo and incoming.titulo:
        existing.titulo = incoming.titulo
    if not existing.alcance and incoming.alcance:
        existing.alcance = incoming.alcance
    existing.refresh_suggestion()


def collect_epc_candidates_from_tables(
    pages_tables: list[list[list[list[str | None]]]],
) -> list[EpcCandidate]:
    """Rebuild logical EPC/BRF rows from extracted tables (page → tables → rows)."""
    by_key: dict[tuple[str, str | None], EpcCandidate] = {}
    current_section: str | None = None
    last_epc: EpcCandidate | None = None
    last_scope: EpcCandidate | None = None

    def store(draft: EpcCandidate) -> None:
        by_key[(draft.brf_key, draft.epc_key)] = draft

    for tables in pages_tables:
        for rows in tables:
            if not rows:
                continue
            header_index, header_kind = _find_header(rows)
            if header_kind == "stop":
                current_section = None
                last_epc = None
                last_scope = None
                continue
            if header_kind is not None:
                current_section = header_kind
            if _looks_like_cover_kv_table(rows):
                continue
            if header_index is not None:
                data_rows = [row for row in rows[header_index + 1 :] if not _looks_like_column_header(row)]
            else:
                data_rows = rows

            if current_section == "epc_table":
                for row in data_rows:
                    _identity_idx, brf_key, _epc_key, _title = _row_identity(row)
                    if brf_key:
                        draft = _new_epc_draft(row)
                        if draft:
                            store(draft)
                            last_epc = draft
                        continue
                    if last_epc is not None:
                        previous_key = (last_epc.brf_key, last_epc.epc_key)
                        _merge_into_draft(last_epc, row)
                        if previous_key != (last_epc.brf_key, last_epc.epc_key):
                            by_key.pop(previous_key, None)
                        store(last_epc)
            elif current_section == "brf_table":
                for row in data_rows:
                    _identity_idx, brf_key, _epc_key, _title = _row_identity(row)
                    if brf_key:
                        incoming = _new_brf_scope_draft(row)
                        if not incoming:
                            continue
                        existing_key = next(
                            (key for key in by_key if key[0] == incoming.brf_key and key[1]),
                            next((key for key in by_key if key[0] == incoming.brf_key), None),
                        )
                        if existing_key:
                            _enrich_from_scope(by_key[existing_key], incoming)
                            last_scope = by_key[existing_key]
                        else:
                            store(incoming)
                            last_scope = incoming
                        continue
                    if last_scope is not None:
                        _merge_into_draft(last_scope, row)

    return list(by_key.values())


def analyze_operativa_rn(pdf_bytes: bytes) -> list[EpcCandidate]:
    """Walk tables in page order, reconstruct split rows, then emit EPC candidates."""
    pages_tables: list[list[list[list[str | None]]]] = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                extracted: list[list[list[str | None]]] = []
                for table in sorted(page.find_tables(), key=lambda t: t.bbox[1]):
                    rows = table.extract()
                    if rows:
                        extracted.append(rows)
                pages_tables.append(extracted)
    except Exception:
        return []
    return collect_epc_candidates_from_tables(pages_tables)
