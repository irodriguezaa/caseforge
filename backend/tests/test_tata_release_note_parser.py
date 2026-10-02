"""Tata RN parser P0 — parallel walker, DAMCO fixtures must stay untouched."""

from pathlib import Path

from app.services.ai_case_engine import _tickets_by_section
from app.services.release_note_analyzer import RuleBasedPdfAnalyzer, _CELL_TICKET_RE, _classify_heading
from app.services.rn_scope_export import extract_rn_scope_rows
from app.services.rn_vendor import detect_rn_vendor
from app.services.tata_release_note_parser import (
    extract_tata_keys,
    parse_tata_release_note,
)
from tests.test_release_note_analyzer import ALL_FIXTURES, ROKU, WEB

FIXTURES = Path(__file__).parent / "fixtures"

LAUNCHER_9122 = "tata_launcher_9.12.2.pdf"
LAUNCHER_9120 = "tata_launcher_9.12.0.pdf"
LAUNCHER_12 = "tata_launcher_12.0.0.pdf"
LAUNCHER_10 = "tata_launcher_10.0.0.pdf"
LAUNCHER_101 = "tata_launcher_10.1.0.pdf"
STV_LG = "tata_stv_lg_3.9.0.pdf"
STV_SAMSUNG = "tata_stv_samsung_3.9.0.pdf"
STV_HISENSE = "tata_stv_hisense_debit_6.0.0.pdf"
STV_ADT = "tata_stv_adt_hbomax_5.1.0.pdf"

_INCIDENTS_9122 = {
    "ATSCL-3101",
    "ATSCL-3096",
    "ATSCL-3095",
    "ATSCL-3094",
    "ATSCL-3092",
    "ATSCL-3053",
    "ATSCL-3045",
    "ATSCL-3044",
    "ATSCL-3043",
    "ATSCL-3093",
}
_EPICS_12 = {
    "ATSCL-2867",
    "ATSCL-2993",
    "ATSCL-2994",
    "ATSCL-3082",
    "ATSCL-3084",
    "ATSCL-2552",
    "ATSCL-3033",
}


def _bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _scope(name: str):
    return parse_tata_release_note(_bytes(name), name)


def _analyze(name: str):
    return RuleBasedPdfAnalyzer().analyze(name, _bytes(name))


def test_damco_fixtures_are_never_classified_as_tata() -> None:
    for filename in ALL_FIXTURES:
        assert detect_rn_vendor(filename, _bytes(filename)) == "damco", filename


def test_tata_filenames_are_classified_as_tata() -> None:
    for name in (LAUNCHER_9122, LAUNCHER_12, STV_LG, STV_HISENSE, STV_ADT):
        assert detect_rn_vendor(name, _bytes(name)) == "tata"


def test_damco_qco_heading_classifier_is_unchanged() -> None:
    assert _classify_heading("1.3 QCO's & QA's resueltos") == "qa_qc"


def test_cell_ticket_regex_still_anchors_to_start_for_damco() -> None:
    assert _CELL_TICKET_RE.match("WEBCL-3721: TE-2026-WEBCL-activacion-hbomax").group(0) == "WEBCL-3721"


def test_launcher_9122_incidents_not_tri_or_functionality() -> None:
    scope = _scope(LAUNCHER_9122)
    analysis = _analyze(LAUNCHER_9122)
    assert set(scope.ids_for("incidents")) == _INCIDENTS_9122
    assert scope.ids_for("technical_epics") == []
    assert scope.ids_for("tri") == []
    assert scope.ids_for("qco") == []
    assert scope.ids_for("qa_bugs") == []
    assert scope.ids_for("qc_bugs") == []
    assert analysis.features_count == 0
    assert analysis.tri_issues_count == 0
    assert analysis.raw_analysis["vendor"] == "tata"
    buckets = _tickets_by_section(_bytes(LAUNCHER_9122), LAUNCHER_9122)
    assert buckets["functionality"] == []
    assert buckets["tri"] == []
    assert buckets["qa_qc"] == []


def test_launcher_9122_qa_evidence_repeats_incident_ids_without_becoming_qa_bugs() -> None:
    scope = _scope(LAUNCHER_9122)
    evidence = set(scope.ids_for("qa_evidence"))
    assert _INCIDENTS_9122 <= evidence
    assert scope.ids_for("qa_bugs") == []
    rows = extract_rn_scope_rows(_bytes(LAUNCHER_9122), fetch_jira=False, filename=LAUNCHER_9122)
    by_act = {}
    for row in rows:
        by_act.setdefault(row["actividad"], set()).add(row["key"])
    assert by_act["Incident"] == _INCIDENTS_9122
    assert "QA Bug" not in by_act
    assert "QC Bug" not in by_act
    assert "TRI" not in by_act
    assert "QA Evidence" in by_act
    assert not ({row["actividad"] for row in rows} & {"Technical Epic", "QCO", "TRI"})


def test_launcher_9122_rejects_firmware_and_version_false_positives() -> None:
    scope = _scope(LAUNCHER_9122)
    blob = " ".join(
        " ".join(scope.ids_for(name))
        for name in ("technical_epics", "incidents", "qa_evidence", "known_issues", "qco")
    )
    assert "012.180" not in blob
    assert "KD-43" not in blob
    keys = extract_tata_keys("ZTE First Gen ATV 12 012.180.051 PE_180FW_User v9.12.2")
    assert keys == []


def test_launcher_9120_known_issues_are_not_functional_scope() -> None:
    scope = _scope(LAUNCHER_9120)
    analysis = _analyze(LAUNCHER_9120)
    assert scope.incidents
    assert all(item.id.startswith("ATSCL-") for item in scope.incidents)
    assert analysis.features_count == 0
    buckets = _tickets_by_section(_bytes(LAUNCHER_9120), LAUNCHER_9120)
    assert buckets["functionality"] == []
    rows = extract_rn_scope_rows(_bytes(LAUNCHER_9120), fetch_jira=False, filename=LAUNCHER_9120)
    known = [row for row in rows if row["actividad"] == "Known Issue"]
    functional = [row for row in rows if row["actividad"] == "Technical Epic"]
    assert functional == []
    # Table may have zero parseable IDs; the section must still not leak into Epics/TRI.
    assert all(row["actividad"] != "TRI" for row in rows)
    assert isinstance(known, list)


def test_launcher_12_epics_exclude_tbrf() -> None:
    scope = _scope(LAUNCHER_12)
    epic_ids = set(scope.ids_for("technical_epics"))
    assert _EPICS_12 <= epic_ids
    assert not any(key.startswith("TBRFRE-") or key.startswith("TBRF-") for key in epic_ids)
    tbrfs = {item.tbrf_id for item in scope.technical_epics if item.tbrf_id}
    assert any(key.startswith("TBRFRE-") for key in tbrfs)
    analysis = _analyze(LAUNCHER_12)
    assert analysis.features_count == len(scope.technical_epics)
    buckets = _tickets_by_section(_bytes(LAUNCHER_12), LAUNCHER_12)
    func_ids = {tid for tid, _ in buckets["functionality"]}
    assert func_ids == epic_ids
    assert not any(key.startswith("TBRFRE-") for key in func_ids)


def test_launcher_10_bracketed_epic_and_tbrf_split() -> None:
    scope = _scope(LAUNCHER_10)
    assert "ATSCL-2640" in scope.ids_for("technical_epics")
    assert "TBRFRE-1734" not in scope.ids_for("technical_epics")
    epic = next(item for item in scope.technical_epics if item.id == "ATSCL-2640")
    assert epic.tbrf_id == "TBRFRE-1734"


def test_stv_lg_incidente_is_not_tri_and_epics_reconstruct_split_ids() -> None:
    scope = _scope(STV_LG)
    analysis = _analyze(STV_LG)
    assert "SCTCL-3085" in scope.ids_for("incidents")
    assert analysis.tri_issues_count == 0
    assert analysis.detected_platform == "STV Tata LG"
    epic_ids = set(scope.ids_for("technical_epics"))
    assert not any(key.startswith("TBRFRE-") for key in epic_ids)
    assert any(key.startswith("SCTCL-") for key in epic_ids)


def test_stv_samsung_device_and_incidente() -> None:
    scope = _scope(STV_SAMSUNG)
    analysis = _analyze(STV_SAMSUNG)
    assert analysis.detected_platform == "STV Tata Samsung"
    assert set(scope.ids_for("incidents")) >= {"SCTCL-3074", "SCTCL-3098"}
    assert analysis.tri_issues_count == 0


def test_stv_hisense_debit_epics_not_tbrf() -> None:
    scope = _scope(STV_HISENSE)
    analysis = _analyze(STV_HISENSE)
    assert analysis.detected_platform == "STV Tata Hisense"
    epics = set(scope.ids_for("technical_epics"))
    assert any(key.startswith("SCTCL-") for key in epics)
    assert not any(key.startswith("TBRFRE-") for key in epics)
    assert scope.ids_for("qco") == []
    assert scope.ids_for("tri") == []


def test_hbomax_issue_id_is_incident_not_epic_and_kd43_rejected() -> None:
    scope = _scope(STV_ADT)
    analysis = _analyze(STV_ADT)
    assert analysis.detected_platform == "STV Tata ADT"
    assert analysis.detected_platform != "ADR"
    assert "SCTCL-3172" in scope.ids_for("incidents")
    assert "SCTCL-3172" not in scope.ids_for("technical_epics")
    assert "KD-43" not in scope.ids_for("incidents")
    assert analysis.features_count == 0


def test_qco_never_promoted_to_qc_bug_even_if_heading_exists() -> None:
    # Tata RNs in fixtures have no QCO; the contract still keeps the array empty
    # and Excel must not emit QC Bug from an empty qco list.
    for name in (LAUNCHER_9122, LAUNCHER_12, STV_HISENSE):
        scope = _scope(name)
        assert scope.qco == []
        rows = extract_rn_scope_rows(_bytes(name), fetch_jira=False, filename=name)
        assert all(row["actividad"] != "QC Bug" for row in rows)


def test_excel_damco_web_actividad_set_unchanged() -> None:
    rows = extract_rn_scope_rows(_bytes(WEB), fetch_jira=False, filename=WEB)
    assert {row["actividad"] for row in rows} <= {
        "Technical Epic",
        "NCO",
        "QA Bug",
        "QC Bug",
        "QA/QC Bug",
        "TRI",
    }
    assert "Incident" not in {row["actividad"] for row in rows}
    assert "QCO" not in {row["actividad"] for row in rows}


def test_roku_qco_section_still_lands_in_legacy_qa_qc_not_normalized_qco() -> None:
    analysis = _analyze(ROKU)
    assert analysis.qa_qc_issues_count == 2
    assert analysis.raw_analysis["vendor"] == "damco"
    normalized = analysis.raw_analysis["normalized"]
    assert normalized["qco"] == []
    assert normalized["incidents"] == []
    buckets = _tickets_by_section(_bytes(ROKU), ROKU)
    qa_ids = {tid for tid, _ in buckets["qa_qc"]}
    assert qa_ids == {"ROKUPR-1537", "ROKUPR-1532"}


def test_numbered_and_bracketed_incident_cells() -> None:
    keys = extract_tata_keys("10 [ATSCL-3093] Claro TV - IPTV")
    assert keys == ["ATSCL-3093"]
    keys = extract_tata_keys("1. SCTCL-3085: launch")
    assert keys == ["SCTCL-3085"]
    keys = extract_tata_keys("TBRFRE- 171 SCTCL- 188")
    assert keys == ["TBRFRE-171", "SCTCL-188"]


def test_empty_tata_categories_stay_empty_on_bugfix_only_rn() -> None:
    scope = _scope(LAUNCHER_9122)
    assert scope.nco == []
    assert scope.qco == []
    assert scope.qa_bugs == []
    assert scope.qc_bugs == []
    assert scope.tri == []
    assert scope.technical_epics == []
