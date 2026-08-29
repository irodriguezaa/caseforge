"""Release Note PDF extraction and structured preparation service.

Validated against 16 real Release Notes spanning WEB, WIN/XBOX, iOS, tvOS, ADR, Roku,
Coship 9085, ADT, FireTV, AAF OTT, and AAF STALE. Design principle: prefer ONE confident,
generic rule per field over a chain of template-specific fallbacks -- a fallback chain is what
previously produced *wrong but confident* values (a truncated name, a SharePoint URL mistaken
for a name, a misdetected device from an incidental keyword). A rule that returns None when it
isn't confident is safer, since the frontend then leaves that field blank for manual entry
instead of silently guessing.

NO intenta reemplazar ni anticipar la lógica del motor QC que se integrará posteriormente desde
el archivo .md (QC Engine). No inventa casos de prueba, estimaciones ni coberturas.

Two libraries, two different jobs:
- pypdf's linear text extraction is used for Version/Description -- plain text patterns that
  don't depend on visual position.
- pdfplumber's coordinate/font data is used for Name (the title is reliably the single
  largest-font text on page 1 across all 16 samples, not just "the first line" -- pypdf's
  linear order can interleave a page-footer artifact or a cover-page field before it) and for
  the 4 counted metrics (Funcionalidades / NCOs / TRIs / QA-QC Bugs), and for Device (evidence
  chain: installation-section heading -> ticket prefix -> title -> filename).
"""

import io
import re
from datetime import date, timedelta
from typing import Any

import pdfplumber
from pypdf import PdfReader

from app.schemas.release import ReleaseAnalysisBase


def calculate_business_days(start_date: date | None, end_date: date | None) -> int:
    """Calculates business days (Monday through Friday only) between start_date and end_date (inclusive)."""
    if not start_date or not end_date or start_date > end_date:
        return 0
    current = start_date
    business_days = 0
    while current <= end_date:
        if current.weekday() < 5:  # 0=Monday, 4=Friday
            business_days += 1
        current += timedelta(days=1)
    return business_days


# --- Device detection: evidence chain, not a single rule ---------------------------------------
# Priority, validated against 16 real RNs:
#   1. "Información de instalación X" section heading (most reliable when present and unique)
#   2. Dominant Jira ticket-key prefix (disambiguates iOS vs tvOS, which share the same
#      installation heading "IOS/TVOS")
#   3. Document title (the ONLY signal that disambiguates ADT vs FireTV, which share BOTH the
#      same installation heading "ADT/FIRE TV" AND the same ticket prefix ADTCL)
#   4. Filename -- last resort only, never primary (per product decision)
#
# IPTV/STB is intentionally NOT implemented as an active rule: the only real-world "evidence"
# found so far (the substring "IPTV" inside one bug ticket's own title, e.g. "ADRPR-1176: IPTV |
# CV | PE || ...") is an incidental business-line tag on a single ticket, not a genuine
# installation-target declaration -- treating it as device evidence would have misclassified a
# real ADR 65.1.9 release. No real IPTV/STB sample RN has been seen yet to validate a rule
# against, so this stays inactive rather than guessed.
_INSTALL_SECTION_RE = re.compile(r"informaci[oó]n de instalaci[oó]n\s*([A-Za-z0-9/\s]+)", re.IGNORECASE)

_INSTALL_SECTION_TO_DEVICE = {
    "ANDROID": "ADR",
    "COSHIP9085": "Coship9085",
    "COSHIP 9085": "Coship9085",
}
# "IOS/TVOS" and "ADT/FIRE TV" installation headings are ambiguous by themselves -- each maps to
# TWO possible devices, disambiguated by ticket prefix or title below.
_AMBIGUOUS_INSTALL_SECTIONS = {
    "IOS/TVOS": {"IOSPR": "iOS", "TVOSPR": "tvOS"},
    "ADT/FIRE TV": None,  # ticket prefix (ADTCL) is identical for both -- title is the only signal
}

_TICKET_PREFIX_TO_DEVICE = {
    "IOSPR": "iOS",
    "TVOSPR": "tvOS",
    "ADRPR": "ADR",
    "C9085PR": "Coship9085",
    "ROKUPR": "Roku",
    "STVCL": "AAF Evolutivo",  # business alias for "AAF OTT"
    "AAFCL": "AAF Legacy",  # business alias for "AAF STALE"
}

_TITLE_KEYWORD_TO_DEVICE = [
    # Order matters: "Android TV" must be checked before a bare "ADT" would ever be (it never
    # appears bare in a title in the real samples, but this keeps intent explicit).
    (re.compile(r"\bFIRE\s*TV\b", re.IGNORECASE), "FireTV"),
    (re.compile(r"\bANDROID\s*TV\b", re.IGNORECASE), "ADT"),
    (re.compile(r"\bAAF\s+OTT\b", re.IGNORECASE), "AAF Evolutivo"),
    (re.compile(r"\bAAF\s+STALE\b", re.IGNORECASE), "AAF Legacy"),
    (re.compile(r"\bROKU\b", re.IGNORECASE), "Roku"),
    (re.compile(r"\bCOSHIP\s*9085\b|\b9085\b", re.IGNORECASE), "Coship9085"),
    (re.compile(r"\bTVOS\b", re.IGNORECASE), "tvOS"),
    (re.compile(r"\bIOS\b", re.IGNORECASE), "iOS"),
    (re.compile(r"\bADR\b", re.IGNORECASE), "ADR"),
    (re.compile(r"\bWINDOWS\s*/\s*XBOX\b|\bXBOX\b", re.IGNORECASE), "WIN/XBOX"),
    (re.compile(r"\bWEB\b", re.IGNORECASE), "WEB"),
]

_FILENAME_ALIASES: dict[str, str] = {
    "WEB": "WEB",
    "XBOX": "WIN/XBOX",
    "WIN": "WIN/XBOX",
    "WINDOWS": "WIN/XBOX",
    "FIRE": "FireTV",
    "ROKU": "Roku",
    "COSHIP": "Coship9085",
    "9085": "Coship9085",
    "IOS": "iOS",
    "TVOS": "tvOS",
    "ADR": "ADR",
}

_TICKET_PREFIX_RE = re.compile(
    r"\b(IOSPR|TVOSPR|ADRPR|C9085PR|ROKUPR|STVCL|AAFCL|ADTCL)-\d+\b"
)


def _detect_device(filename: str, text: str, detected_name: str | None) -> str | None:
    # 1. Installation-section heading.
    install_match = _INSTALL_SECTION_RE.search(text)
    ticket_prefixes = [m.upper() for m in _TICKET_PREFIX_RE.findall(text)]
    dominant_prefix = max(set(ticket_prefixes), key=ticket_prefixes.count) if ticket_prefixes else None

    if install_match:
        section = install_match.group(1).strip().upper()
        section = re.sub(r"\s+", " ", section)
        if section in _INSTALL_SECTION_TO_DEVICE:
            return _INSTALL_SECTION_TO_DEVICE[section]
        if section == "ADT/FIRE TV":
            # Ticket prefix (ADTCL) is identical for ADT and FireTV -- the actual TITLE (not a
            # raw text window, which would also catch this same TOC entry mentioning both
            # devices together) is the only signal that disambiguates.
            title = detected_name or ""
            for pattern, device in _TITLE_KEYWORD_TO_DEVICE:
                if pattern.search(title):
                    if device in ("ADT", "FireTV"):
                        return device
            return None  # genuinely ambiguous -- do not guess
        if section in _AMBIGUOUS_INSTALL_SECTIONS:
            mapping = _AMBIGUOUS_INSTALL_SECTIONS[section]
            if mapping and dominant_prefix in mapping:
                return mapping[dominant_prefix]

    # 2. Dominant ticket-key prefix.
    if dominant_prefix and dominant_prefix in _TICKET_PREFIX_TO_DEVICE:
        return _TICKET_PREFIX_TO_DEVICE[dominant_prefix]

    # 3. Document title.
    title = detected_name or text[:300]
    for pattern, device in _TITLE_KEYWORD_TO_DEVICE:
        if pattern.search(title):
            return device

    # 4. Filename -- last resort only.
    normalized = re.sub(r"[_\s]+", " ", filename).upper()
    tokens = set(re.split(r"[-\s]+", normalized))
    for alias, canonical in _FILENAME_ALIASES.items():
        if alias in tokens:
            return canonical

    return None


# --- Name: largest-font text on page 1, not "the first line" of linear text --------------------
def _detect_name_from_page1(pdf_bytes: bytes) -> str | None:
    """The title is reliably the single largest-font text block on page 1 across all 16 real
    samples checked (14.3pt vs 11.1pt body text vs 8.2pt TOC entries) -- using visual structure
    instead of pypdf's linear text order avoids picking up a page-footer artifact or a cover-page
    table cell that happens to come first in extraction order."""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            if not pdf.pages:
                return None
            page = pdf.pages[0]
            chars = page.chars
            if not chars:
                return None
            lines: dict[int, list] = {}
            for char in chars:
                lines.setdefault(round(char["top"]), []).append(char)

            best_top, best_size, best_text = None, -1.0, None
            for top, line_chars in lines.items():
                size = max(c["size"] for c in line_chars)
                if size > best_size:
                    text = "".join(c["text"] for c in sorted(line_chars, key=lambda c: c["x0"]))
                    best_top, best_size, best_text = top, size, text

            if not best_text:
                return None
            candidate = best_text.strip()
            if len(candidate) < 5 or len(candidate) > 150 or "http" in candidate.lower():
                return None
            return candidate
    except Exception:
        return None


# Anchored to the "1.N" numbered subsection convention (several templates use it, in different
# orders per template) -- classification is by the heading's own KEYWORD, never its position
# number.
_NUMBERED_HEADING_RE = re.compile(r"^\s*1\.\d+\s*\)?\s*(.+)$")

# Layer 2 fallback, used only when a document has NO numbered "1.N" headings at all.
_QA_QC_SENTENCE_RE = re.compile(r"(defectos\s+QA\s+y\s+QC|QA\s*/\s*QC|corrige\s+defectos)", re.IGNORECASE)

# Only the ticket that HEADS a table cell counts -- a cell's own descriptive text can mention
# another ticket inline.
_CELL_TICKET_RE = re.compile(r"^\s*(?!BRF)([A-Z]{2,8})-(\d{2,6})")

# The Table of Contents repeats the "Descripción del cambio" header before the real section, so
# the LAST occurrence in the document is used. The stop boundary is the next numbered heading of
# ANY level, since not all templates continue into "1.1" (some go straight to "2.").
_DESCRIPTION_HEADER_RE = re.compile(r"descripci[oó]n del cambio", re.IGNORECASE)
_NEXT_NUMBERED_HEADING_RE = re.compile(r"\n\s*\d+\s*[\.\)]")


def _detect_description(text: str) -> str | None:
    header_matches = list(_DESCRIPTION_HEADER_RE.finditer(text))
    if not header_matches:
        return None
    start = header_matches[-1].end()
    remainder = text[start:]
    stop_match = _NEXT_NUMBERED_HEADING_RE.search(remainder)
    body = remainder[: stop_match.start()] if stop_match else remainder
    body = body.strip()
    # Several templates (hotfix/mundial-phase RNs) have NO real description paragraph at all --
    # only the bare section header immediately followed by the next heading or a metadata table.
    # A body this short is the header's own leftover punctuation, not real content.
    if len(body) < 15:
        return None
    return body


def _table_header_override(header_cell: str) -> str | None:
    """A table's OWN header cell, when it's one of these exact/specific phrases, is a stronger
    and more direct signal than the numbered-heading position tracking -- used for documents
    where the real numbered heading is undetectable by position (merged into a giant cover-page
    table cell, e.g. iOS 10.1.5) or where a real sub-section has no numbered heading at all
    (e.g. ADR's un-numbered "SWATT NEORIS" -> TRI table).

    Deliberately narrow: "TRI" and "QA bugs / QC bugs" were verified, across all 17 real RN
    samples checked, to NEVER be reused as a header for any other section. "ARTEFACTO"/"BRF"
    were explicitly tried and rejected for this same purpose -- they're also used as the header
    for "Alcance no entregado" / "Histórico de versiones" tables in several templates, which
    would silently pull that unrelated content into Functionality.
    """
    normalized = header_cell.strip().upper().replace("ʼ", "'").replace("’", "'")
    if normalized == "TRI":
        return "tri"
    if "QA BUGS" in normalized and "QC BUGS" in normalized:
        return "qa_qc"
    return None


def _classify_heading(label: str) -> str | None:
    # Typographic apostrophes (ʼ ’ `) are Unicode word characters to Python's regex engine,
    # which silently breaks \b word-boundary matching (e.g. "NCOʼs" reads as one word "NCOʼs",
    # so \bNCO\b never matches). Normalizing to a plain ASCII apostrophe first fixes this
    # generally, not just for one specific heading's exact wording.
    normalized_label = label.replace("ʼ", "'").replace("’", "'").replace("`", "'")
    upper = normalized_label.upper()
    if re.search(r"\bNCO\b", upper):
        return "nco"
    if "QA-QC" in upper or "QCO" in upper or ("QA" in upper and "'" in normalized_label):
        return "qa_qc"
    if "DEFECTOS ENCONTRADOS" in upper:
        # ADR / tvOS / Coship9085 / Android-TV(HF) templates use this instead of a "QA-QC" or
        # "QCO" heading for the exact same QA bugs / QC bugs table.
        return "qa_qc"
    if "PRODUCTIV" in upper or re.search(r"\bTRI\b", upper):
        return "tri"
    if "FUNCIONALIDAD" in upper:
        return "functionality"
    if upper.strip() == "RELEASE":
        # Same template family uses a bare "1.1 Release" heading (not "Funcionalidad
        # Incluida") directly above the functionality table.
        return "functionality"
    return None  # "Alcance no entregado" / "Histórico..." / "Incidencias Conocidas" -- untracked


class TableCounts:
    __slots__ = ("functionality", "nco", "tri", "qa_qc")

    def __init__(self, functionality: int = 0, nco: int = 0, tri: int = 0, qa_qc: int = 0) -> None:
        self.functionality = functionality
        self.nco = nco
        self.tri = tri
        self.qa_qc = qa_qc


class RuleBasedPdfAnalyzer:
    """Deterministic extractor for Release Note PDF documents."""

    def extract_text(self, pdf_bytes: bytes) -> str:
        try:
            reader = PdfReader(io.BytesIO(pdf_bytes))
            pages_text: list[str] = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)
            return "\n".join(pages_text)
        except Exception:
            return ""

    def _extract_table_counts(self, pdf_bytes: bytes) -> TableCounts:
        """Reads every table on every page via pdfplumber's coordinate-based detection,
        interleaved with numbered-heading text found at real page positions -- not by pypdf's
        linear text, which corrupts page-break continuations. A table with no section change
        since the last heading (a page-break continuation) inherits the current section.

        Layer 2: if the WHOLE document has no numbered "1.N" heading at all, the first table
        containing ticket-headed cells defaults to Functionality, and a free-text QA/QC-defects
        sentence marks the QA/QC table.
        """
        counts: dict[str, set[str]] = {"functionality": set(), "nco": set(), "tri": set(), "qa_qc": set()}
        current_section: str | None = None
        any_numbered_heading_found = False

        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages:
                    events: list[tuple[float, str, Any]] = []

                    words = page.extract_words()
                    lines: dict[int, list] = {}
                    for word in words:
                        lines.setdefault(round(word["top"]), []).append(word)
                    for top, line_words in lines.items():
                        line_words.sort(key=lambda w: w["x0"])
                        line_text = " ".join(w["text"] for w in line_words)
                        heading_match = _NUMBERED_HEADING_RE.match(line_text)
                        if heading_match:
                            events.append((top, "heading", _classify_heading(heading_match.group(1))))
                        elif _QA_QC_SENTENCE_RE.search(line_text):
                            events.append((top, "qa_sentence", None))

                    for table in page.find_tables():
                        events.append((table.bbox[1], "table", table))

                    events.sort(key=lambda e: e[0])

                    # A Table of Contents is a run of 3+ consecutive "heading" events, closely
                    # spaced vertically (consistent line height, like a real TOC's line spacing)
                    # with no table/content event between them -- it lists section names but
                    # doesn't start real content, so it must not be allowed to overwrite
                    # current_section. The vertical-closeness check matters: without it, a real
                    # TOC block followed much later by an isolated real heading (with no table
                    # event happening to fall between them) would wrongly merge into one run and
                    # skip the real heading too.
                    _toc_line_gap_px = 50
                    toc_indices: set[int] = set()
                    run: list[int] = []

                    def _flush_run() -> None:
                        if len(run) >= 3:
                            toc_indices.update(run)
                        run.clear()

                    last_heading_top: float | None = None
                    for i, event in enumerate(events):
                        if event[1] == "heading":
                            top = event[0]
                            if run and last_heading_top is not None and top - last_heading_top > _toc_line_gap_px:
                                _flush_run()
                            run.append(i)
                            last_heading_top = top
                        else:
                            _flush_run()
                            last_heading_top = None
                    _flush_run()

                    for idx, (_top, kind, payload) in enumerate(events):
                        if kind == "heading":
                            if idx not in toc_indices and payload is not None:
                                current_section = payload
                                any_numbered_heading_found = True
                            continue
                        if kind == "qa_sentence":
                            current_section = "qa_qc"
                            continue

                        rows = payload.extract()
                        if not rows:
                            continue
                        header_cell = (rows[0][0] or "").strip()
                        override = _table_header_override(header_cell)

                        tickets_here: set[str] = set()
                        for row in rows:
                            for cell in row:
                                if not cell:
                                    continue
                                match = _CELL_TICKET_RE.match(cell)
                                if match:
                                    tickets_here.add(f"{match.group(1)}-{match.group(2)}")
                        if not tickets_here:
                            continue

                        if override is not None:
                            # The table's own header is a stronger, more direct signal than
                            # whatever the sticky numbered-heading state currently says -- and
                            # it becomes the new sticky state itself, so a header-less
                            # continuation of THIS table (e.g. ADR's TRI table spanning pages
                            # 2-6 with the header only printed once) still counts correctly.
                            current_section = override
                            bucket = override
                        else:
                            bucket = current_section
                            if bucket is None and not any_numbered_heading_found:
                                # No numbered heading has EVER been found in this document --
                                # the first ticket-bearing table defaults to Functionality, and
                                # (unlike the previous one-shot version) STAYS Functionality for
                                # subsequent header-less continuation tables too, since nothing
                                # else in the document will ever signal otherwise.
                                bucket = "functionality"
                                current_section = "functionality"
                        if bucket in counts:
                            counts[bucket] |= tickets_here
        except Exception:
            pass  # Table extraction is best-effort; a malformed PDF just yields all-zero counts.

        return TableCounts(
            functionality=len(counts["functionality"]),
            nco=len(counts["nco"]),
            tri=len(counts["tri"]),
            qa_qc=len(counts["qa_qc"]),
        )

    def analyze(self, filename: str, pdf_bytes: bytes) -> ReleaseAnalysisBase:
        text = self.extract_text(pdf_bytes)
        table_counts = self._extract_table_counts(pdf_bytes)
        detected_name = _detect_name_from_page1(pdf_bytes)
        return self._build_analysis(filename, text, table_counts, detected_name)

    def _build_analysis(
        self, filename: str, text: str, table_counts: TableCounts, detected_name: str | None
    ) -> ReleaseAnalysisBase:
        """Text-in, structured-analysis-out -- split from analyze() so Version/Description
        rules can be unit-tested directly against a known text sample, independent of the
        coordinate-based Name/table extraction."""
        observations: list[str] = []

        # Version -- captures the whole prefix+number span verbatim (e.g. "OTT- 25.4.0",
        # "Stale- 25.4.0", "V6.0.0", "10.1.7b2") rather than assuming a fixed separator, so it
        # doesn't invent formatting the source document didn't actually use.
        detected_version = None
        version_match = re.search(
            r"(?<!\bla )(?<!\buna )(?<!\besta )(?<!\bde )(?<!\bde la )"
            r"(?:versi[oó]n|ver\.?)\s*[:\-]?\s*([A-Za-z]*[\-\s]*[0-9]+\.[0-9]+(?:\.[0-9]+)?[a-z]?\d*)",
            text,
            re.IGNORECASE,
        )
        if version_match:
            detected_version = re.sub(r"\s+", "", version_match.group(1).strip())
        else:
            fn_version_match = re.search(r"v?([0-9]+\.[0-9]+(?:\.[0-9]+)?)", filename)
            if fn_version_match:
                detected_version = fn_version_match.group(1).strip()

        detected_platform = _detect_device(filename, text, detected_name)
        detected_description = _detect_description(text)

        if not text:
            observations.append("El archivo PDF no contiene texto extraíble (puede ser un documento escaneado o protegido).")
        else:
            if not detected_name:
                observations.append("No se pudo determinar el Nombre con certeza; captúrelo manualmente.")
            if not detected_platform:
                observations.append("No se detectó un dispositivo reconocido con suficiente evidencia; selecciónelo manualmente.")
            if not detected_version:
                observations.append("No se detectó el número de versión en el documento; ingréselo manualmente.")
            if not detected_description:
                observations.append("No se pudo determinar la Descripción con certeza; captúrela manualmente.")
            if table_counts.functionality > 0:
                observations.append(f"Se detectaron {table_counts.functionality} elemento(s) en la tabla de Funcionalidades.")
            if table_counts.qa_qc > 0:
                observations.append(f"Se identificaron {table_counts.qa_qc} incidencia(s) QA/QC Bugs.")
            if table_counts.nco > 0:
                observations.append(f"Se identificaron {table_counts.nco} incidencia(s) NCO.")
            if table_counts.tri > 0:
                observations.append(f"Se identificaron {table_counts.tri} incidencia(s) productiva(s) (TRI).")

        raw_analysis = {
            "text_length": len(text),
            "pages_analyzed": len(text.split("\n\n")),
            "filename": filename,
        }

        return ReleaseAnalysisBase(
            pdf_filename=filename,
            detected_name=detected_name,
            detected_version=detected_version,
            detected_platform=detected_platform,
            detected_description=detected_description,
            features_count=table_counts.functionality,
            qa_qc_issues_count=table_counts.qa_qc,
            nco_issues_count=table_counts.nco,
            tri_issues_count=table_counts.tri,
            detected_devices=detected_platform,
            proposed_coverage=None,  # Será responsabilidad del QC Engine (.md) futuro
            estimation_text=None,    # Será responsabilidad del QC Engine (.md) futuro
            observations=observations,
            raw_analysis=raw_analysis,
            qc_engine_version="v0.1",
        )
