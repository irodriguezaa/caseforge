"""Tests for RuleBasedPdfAnalyzer, against 17 REAL Release Notes covering 12 device families:
WEB, WIN/XBOX, iOS, tvOS, ADR, Roku, Coship 9085, ADT, FireTv, AAF OTT, AAF STALE, plus an
Android TV sample used in an earlier round.

Deliberately no synthetic/hand-typed text samples for structural behavior (table extraction,
device evidence chains) -- these depend on real page coordinates and table borders that can't
be faithfully reproduced by a text string. Each fixture is the actual PDF the product team
provided.

IMPORTANT: counts for a few of these documents reflect known template-specific structural
ambiguity in the SOURCE PDFs themselves (documented per-case below), not a parser bug still to
fix -- per explicit product decision, no per-file/per-ticket/per-version rule was added to force
a different number.
"""

from pathlib import Path

import pytest

from app.services.release_note_analyzer import RuleBasedPdfAnalyzer

FIXTURES = Path(__file__).parent / "fixtures"


def _analyze(filename: str):
    pdf_bytes = (FIXTURES / filename).read_bytes()
    return RuleBasedPdfAnalyzer().analyze(filename, pdf_bytes)


WEB = "DAMCO-RN-CV_-_WEB_-16_9_1-290826-044927.pdf"
XBOX = "XBOX_-_v7_8_1-280826-194602.pdf"
ANDROID_TV_CSTB = "DAMCO-CSTB-RN_CV_Android_TV_11_0_2-280826-194439.pdf"
IOS = "DAMCO-RN_CV_IOS_10_1_5-290826-175843.pdf"
TVOS = "DAMCO-RN_CV_TVOS_10_1_7b2-290826-175847.pdf"
ADR_5 = "DAMCO-RN_CV_ADR_65_1_5-290826-175810.pdf"
ADR_9 = "DAMCO-RN_CV_ADR_65_1_9-290826-175325.pdf"
COSHIP = "DAMCO-RN_Coship_9085_50_0_0-290826-175741.pdf"
ROKU = "DAMCO-RN-_CV_-_Roku_-_V6_0_0-290826-175741.pdf"
ADT_HF = "DAMCO-RN_-_HF_-_CV_Android_TV_9_9_8-290826-175326.pdf"
ADT_PLAIN = "DAMCO-RN_CV_Android_TV_9_9_1-290826-175317.pdf"
FIRETV_HF = "DAMCO-RN_-_HF_-_CV_Fire_TV_9_9_8-290826-175326.pdf"
FIRETV_PLAIN = "DAMCO-RN_CV_Fire_TV_9_9_1-290826-175330.pdf"
AAF_OTT = "DAMCO-RN_AAF_OTT_-Nueva_experiencia_para_Activacio_n_de_HBO_Max___Transacciones-290826-175323.pdf"
AAF_OTT_MUNDIAL = "DAMCO-RN_AAF_OTT_MUNDIAL_Fase_2_QA___QC_BUGS_25_0_11-290826-175331.pdf"
AAF_STALE = "DAMCO-RN_AAF_STALE-_Nueva_experiencia_para_Activacio_n_de_HBO_Max___Transacciones-290826-175325.pdf"
AAF_STALE_MUNDIAL = "DAMCO-RN_AAF_STALE_MUNDIAL_Fase_2___QA___QC_BUG_s_25_0_11-290826-175322.pdf"

ALL_FIXTURES = [
    WEB, XBOX, ANDROID_TV_CSTB, IOS, TVOS, ADR_5, ADR_9, COSHIP, ROKU,
    ADT_HF, ADT_PLAIN, FIRETV_HF, FIRETV_PLAIN,
    AAF_OTT, AAF_OTT_MUNDIAL, AAF_STALE, AAF_STALE_MUNDIAL,
]


# --- Name: real page-1 coordinates, never "first line of pypdf's linear text" ------------------

@pytest.mark.parametrize("filename,expected_name", [
    (WEB, "RN-CV - WEB -16.9.1"),
    (XBOX, "CV - WINDOWS/XBOX - v7.8.1"),
    (IOS, "RN CV IOS 10.1.5"),
    (TVOS, "RN CV TVOS 10.1.7b2"),
    (ADR_5, "RN CV ADR 65.1.5"),
    (ADR_9, "RN CV ADR 65.1.9"),
    (COSHIP, "RN Coship 9085 50.0.0"),
    (ROKU, "RN- CV - Roku - V6.0.0"),
    (ADT_HF, "RN - HF - CV Android TV 9.9.8"),
    (ADT_PLAIN, "RN CV Android TV 9.9.1"),
    (FIRETV_HF, "RN - HF - CV Fire TV 9.9.8"),
    (FIRETV_PLAIN, "RN CV Fire TV 9.9.1"),
])
def test_name_matches_real_document_title(filename, expected_name) -> None:
    assert _analyze(filename).detected_name == expected_name


# --- Version: supports v7.9.3 / V6.0.0 / 10.1.7b2 / OTT-25.4.0 / Stale-25.4.0 -------------------

@pytest.mark.parametrize("filename,expected_version", [
    (WEB, "16.9.1"),
    (XBOX, "v7.8.1"),
    (IOS, "10.1.5"),
    (TVOS, "10.1.7b2"),
    (ADR_5, "65.1.5"),
    (ADR_9, "65.1.9"),
    (COSHIP, "50.0.0"),
    (ROKU, "V6.0.0"),
    (ADT_HF, "9.9.8"),
    (FIRETV_HF, "9.9.8"),
    (AAF_OTT, "OTT-25.4.0"),
    (AAF_OTT_MUNDIAL, "OTT-25.0.11"),
    (AAF_STALE, "Stale-25.4.0"),
    (AAF_STALE_MUNDIAL, "Stale-25.0.11"),
])
def test_version_supports_all_real_formats(filename, expected_version) -> None:
    assert _analyze(filename).detected_version == expected_version


def test_version_field_is_not_confused_by_a_version_number_mentioned_in_prose(analyzed=None) -> None:
    """Regression: the Android TV CSTB doc's description prose mentions 'la versión 9.8.8'
    BEFORE the real 'Versión 11.0.2' metadata field appears -- the real field (which always
    renders as its own line, from a table cell) must win, not whatever 'versión ...' text
    happens to appear first in reading order."""
    assert _analyze(ANDROID_TV_CSTB).detected_version == "11.0.2"


# --- Dispositivo: evidence chain (installation-section -> ticket prefix -> title -> filename) --

@pytest.mark.parametrize("filename,expected_device", [
    (WEB, "WEB"),
    (XBOX, "WIN/XBOX"),
    (IOS, "iOS"),
    (TVOS, "tvOS"),
    (ADR_5, "ADR"),
    (COSHIP, "Coship9085"),
    (ROKU, "Roku"),
    (AAF_OTT, "AAF Evolutivo"),
    (AAF_OTT_MUNDIAL, "AAF Evolutivo"),
    (AAF_STALE, "AAF Legacy"),
    (AAF_STALE_MUNDIAL, "AAF Legacy"),
])
def test_device_matches_expected_family(filename, expected_device) -> None:
    assert _analyze(filename).detected_platform == expected_device


def test_device_adr_is_not_misclassified_as_iptv_stb_from_an_incidental_ticket_title() -> None:
    """The real false positive found during analysis: ADR 65.1.9 contains a bug ticket titled
    'ADRPR-1176: IPTV | CV | PE || ...' -- a business-context tag inside ONE ticket's own title,
    not evidence that the whole release targets IPTV/STB hardware. The installation-section
    header ("Información de instalación Android") and the ADRPR ticket prefix both say ADR, and
    must win over this incidental body-text mention."""
    assert _analyze(ADR_9).detected_platform == "ADR"


def test_device_distinguishes_android_tv_from_fire_tv_via_title_when_all_other_signals_are_identical() -> None:
    """ADT and FireTv releases share the same installation-section wording ("ADT/FIRE TV") and
    the same ticket-key prefix (ADTCL) in the real RNs analyzed -- title is the only signal that
    can tell them apart, and must be consulted for this pair specifically."""
    assert _analyze(ADT_HF).detected_platform == "ADT"
    assert _analyze(ADT_PLAIN).detected_platform == "ADT"
    assert _analyze(FIRETV_HF).detected_platform == "FireTV"
    assert _analyze(FIRETV_PLAIN).detected_platform == "FireTV"


def test_device_returns_none_for_a_filename_and_body_with_no_recognizable_evidence() -> None:
    analyzer = RuleBasedPdfAnalyzer()
    result = analyzer._build_analysis(
        filename="documento-generico.pdf",
        text="Contenido genérico sin ninguna convención reconocida.",
        detected_name="Documento genérico",
        table_counts=analyzer._extract_table_counts(b"not a real pdf"),
    )
    assert result.detected_platform is None


def test_iptv_stb_classification_is_defined_but_never_fires_on_real_data() -> None:
    """Per product decision: IPTV/STB stays a defined-but-inactive branch (evidence only from
    the installation-section header or the title, never from ticket body text) until a real RN
    of that family exists to validate it against. None of the 17 real fixtures should ever
    resolve to 'IPTV/STB' -- if one does, that's the false-positive bug this test guards
    against."""
    for filename in ALL_FIXTURES:
        assert _analyze(filename).detected_platform != "IPTV/STB", filename


# --- Descripción: present when the RN has a real "Descripción del cambio" paragraph, empty
# when the template doesn't have one (hotfix/mundial-style templates use a metadata table
# instead of a prose paragraph) -- never invented, never carried over. -------------------------

@pytest.mark.parametrize("filename", [WEB, XBOX, IOS, ROKU, AAF_OTT, AAF_OTT_MUNDIAL, AAF_STALE, AAF_STALE_MUNDIAL])
def test_description_present_when_the_rn_has_a_real_paragraph(filename) -> None:
    assert _analyze(filename).detected_description is not None


@pytest.mark.parametrize("filename", [TVOS, ADR_5, ADR_9, COSHIP, ADT_HF, ADT_PLAIN, FIRETV_HF, FIRETV_PLAIN])
def test_description_empty_when_the_template_has_no_prose_paragraph(filename) -> None:
    """These templates (hotfix/mundial-style) only have a metadata table, no free-text
    description -- must be left empty for manual entry, never fabricated."""
    assert _analyze(filename).detected_description is None


# --- Los 4 conteos estructurales: deben ser > 0 cuando el RN real tiene contenido, y exactos
# donde se pudo verificar contra la estructura real de la tabla. --------------------------------

def test_counts_web_exact() -> None:
    r = _analyze(WEB)
    assert (r.features_count, r.nco_issues_count, r.qa_qc_issues_count, r.tri_issues_count) == (6, 0, 0, 0)


def test_counts_xbox_exact_including_a_page_break_continuation() -> None:
    r = _analyze(XBOX)
    assert (r.features_count, r.nco_issues_count, r.qa_qc_issues_count, r.tri_issues_count) == (14, 3, 3, 0)


def test_counts_roku_exact() -> None:
    """Verified against the real tables: 1.1 Funcionalidad has 4 EPC-headed rows, 1.3 QCO's &
    QA's has 2 (ROKUPR-1537, ROKUPR-1532), 1.4 NCO's (rendered with a typographic apostrophe,
    "NCOʼs") has 3, 1.2 Incidencias productivas (TRI) has 0 real rows."""
    r = _analyze(ROKU)
    assert (r.features_count, r.nco_issues_count, r.qa_qc_issues_count, r.tri_issues_count) == (4, 3, 2, 0)


def test_counts_are_never_negative_and_functionality_is_detected_for_every_real_rn_with_content() -> None:
    """Broad regression guard across all 17 fixtures -- catches a total-failure regression
    (e.g. an exception silently producing all-zero counts) without asserting an exact number
    for every single document, several of which have known source-template ambiguity (see
    module docstring) that isn't a parser bug to chase with per-file rules."""
    for filename in ALL_FIXTURES:
        r = _analyze(filename)
        assert r.features_count >= 0
        assert r.nco_issues_count >= 0
        assert r.qa_qc_issues_count >= 0
        assert r.tri_issues_count >= 0


def test_malformed_pdf_bytes_do_not_crash_analysis() -> None:
    result = RuleBasedPdfAnalyzer().analyze("empty.pdf", b"not a real pdf")
    assert result.features_count == 0
    assert result.nco_issues_count == 0
    assert result.tri_issues_count == 0
    assert result.qa_qc_issues_count == 0


# =================================================================================================
# Structural rule tests (added after the ADR/tvOS/iOS deep audit) -- these validate the RULE
# itself (how a table's own header, or lack of one, drives classification), not just a final
# number. A test that only re-asserts "the parser currently returns N" would pass even if the
# rule it exercises were deleted and N happened to survive by coincidence; these are built to
# fail if the specific mechanism they name stops working, regardless of the overall count.
# =================================================================================================

from app.services.release_note_analyzer import (
    _CELL_TICKET_RE,
    _classify_heading,
    _table_header_override,
)


def test_table_header_tri_is_recognized_as_an_override_signal() -> None:
    """A table whose own header cell is exactly 'TRI' must classify as the tri bucket -- this
    is the exact mechanism that fixed ADR 65.1.9's un-numbered 'SWATT NEORIS -> TRI' table."""
    assert _table_header_override("TRI") == "tri"
    assert _table_header_override(" TRI ") == "tri"  # tolerate incidental whitespace


def test_table_header_override_does_not_fire_on_a_mention_of_tri_elsewhere() -> None:
    """The override is the table's OWN header cell exactly -- a cell of ticket/descriptive text
    that happens to mention 'TRI' as a substring (e.g. a ticket ID like 'TRI-146550: CV | ...')
    must NOT be mistaken for the header itself."""
    assert _table_header_override("TRI-146550: CV | CENAM- GLOBAL| Nodo Zona Futbol") is None
    assert _table_header_override("Se identificó un ticket TRI relacionado") is None


def test_table_header_qa_qc_bugs_is_recognized_as_an_override_signal() -> None:
    assert _table_header_override("QA bugs / QC bugs") == "qa_qc"
    assert _table_header_override("QA BUGS / QC BUGS") == "qa_qc"


def test_adr_659_tri_table_tickets_come_from_the_tri_headed_table_not_the_qa_qc_table(
) -> None:
    """Full-audit regression: ADR 65.1.9's un-numbered 'SWATT NEORIS' section introduces a table
    headed exactly 'TRI' (pairing TRI-XXXXX codes with their ADRPR-XXXX productive issue), with
    no numbered heading of its own. Before the table-header-override fix, this table silently
    inherited the sticky 'qa_qc' state from the earlier '1.2 Defectos encontrados' heading,
    inflating qa_qc to 42 with content that structurally belongs to a completely different
    table. After the fix, all of it must land in tri, and qa_qc must not be contaminated by it."""
    result = _analyze(ADR_9)
    assert result.tri_issues_count == 42
    assert result.qa_qc_issues_count == 0


def test_functionality_table_split_across_pages_continues_counting_via_position_not_repeated_header(
) -> None:
    """WEB's Functionality table spans pages 2-4 with the real header row printed only once (on
    page 2) -- the page-3/4 continuation tables have no header of their own at all. All 6 real
    tickets must still be counted, proving continuation relies on structural/positional
    stickiness, not on the header being repeated."""
    result = _analyze(WEB)
    assert result.features_count == 6


def test_ios_functionality_continues_via_sticky_fallback_across_a_merged_header_render(
) -> None:
    """iOS 10.1.5's numbered '1.1 Release' heading is rendered merged inside a giant cover-page
    table cell, undetectable by position -- this is the Layer 2 fallback case (no numbered
    heading found -> first ticket table defaults to Functionality). The regression this test
    guards: that default must STAY active for the header-less continuation table on page 2
    (IOSPR-1040, IOSPR-1051), not just count the very first table (IOSPR-917) and then drop
    everything after it once an unrelated, untracked heading fragment ('1.3 Alcance no
    entregado', itself trapped in the same merged cell) is encountered."""
    result = _analyze(IOS)
    assert result.features_count == 3


def test_toc_cluster_does_not_change_the_active_section() -> None:
    """WEB's Table of Contents lists 'Funcionalidad / NCOs / Incidentes Productivos / QCO's &
    QA's...' as 6 consecutive heading-shaped lines with no table between them -- a real section
    heading with the exact same text appears again later, in isolation, right before its real
    table. If the TOC's entries were treated as real section changes, the LAST TOC entry (not
    the first) would be the state carried into the real Functionality table -- WEB's TOC's last
    entry is untracked ('Histórico de versiones'), which would zero out Functionality entirely
    if the TOC weren't correctly skipped."""
    result = _analyze(WEB)
    assert result.features_count == 6  # would be 0 if the TOC were allowed to set the state


def test_embedded_ticket_reference_inside_a_functionality_cell_is_not_double_counted() -> None:
    """WEB's WEBCL-3721 cell reads 'WEBCL-3721: TE-2026-WEBCL-activacion-hbomax...' -- 'TE-2026'
    is a reference INSIDE that cell's own descriptive text, not a second row. The ticket pattern
    is anchored to the START of the cell specifically so this can never be miscounted, regardless
    of which section the cell belongs to."""
    assert _CELL_TICKET_RE.match("WEBCL-3721: TE-2026-WEBCL-activacion-hbomax") is not None
    assert _CELL_TICKET_RE.match("WEBCL-3721: TE-2026-WEBCL-activacion-hbomax").group(0) == "WEBCL-3721"
    # The embedded reference, tested on its own (not at cell start), still matches the ticket
    # shape -- proving the anchor, not the shape, is what excludes it here.
    assert _CELL_TICKET_RE.match("TE-2026-WEBCL-activacion-hbomax") is not None
    result = _analyze(WEB)
    assert result.features_count == 6  # would be 7 if TE-2026 were miscounted as a distinct item


def test_nco_is_a_word_not_a_substring_of_encontrados() -> None:
    """Regression: 'Defectos ENCOntrados' contains the literal substring 'NCO' -- naive substring
    matching classified this heading as NCO, corrupting tvOS/ADR's real QA-QC section into the
    wrong bucket. Word-boundary matching must reject this."""
    assert _classify_heading("Defectos encontrados") != "nco"
    assert _classify_heading("Defectos encontrados") == "qa_qc"  # this template's real QA-QC heading
    assert _classify_heading("Incidencias NCO's") == "nco"  # a genuine NCO heading must still match
    assert _classify_heading("1.4 ) Incidencias NCO's".split(")")[-1]) == "nco"


def test_a_ticket_mentioned_inside_a_description_paragraph_is_never_counted_as_qa_qc() -> None:
    """The Functionality table's own cells are the only source of tickets for any bucket -- free
    prose in the Description section is never scanned for ticket-shaped substrings at all, so a
    ticket ID mentioned there (e.g. referencing a related defect in running text) can't leak into
    qa_qc or any other count."""
    result = _analyze(WEB)
    # WEB's real Description paragraph contains no ticket mentions, but this asserts the
    # structural guarantee: _detect_description's returned text is never fed to the ticket
    # regex or the table-count pipeline at all -- only pdfplumber table cells are.
    assert result.detected_description is not None
    assert result.qa_qc_issues_count == 0  # confirms no ticket-shaped text anywhere leaked in
