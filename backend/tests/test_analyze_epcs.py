"""Pasted Technical Epic list → same analysis spine as RN. Does not touch Operativa Epc."""

from pathlib import Path

from sqlalchemy import select

from app.models.epc import Epc
from app.services.epc_paste import parse_epc_paste, tickets_from_normalized_technical_epics
from app.services.release_note_analyzer import RuleBasedPdfAnalyzer

WEB_RN = Path(__file__).parent / "fixtures" / "DAMCO-RN-CV_-_WEB_-16.9.0-010926-005137.pdf"


def _artifact(key: str, *, issuetype: str = "Technical Epic", summary: str | None = None) -> dict:
    return {
        "key": key,
        "issuetype": issuetype,
        "summary": summary or f"Summary {key}",
        "status": "QA Validation",
        "description": f"Feature: {key}\nScenario: demo\n  When x\n  Then y",
        "acceptance_criteria": "El usuario ve el resultado",
        "children": [
            {
                "key": f"{key}-C",
                "issuetype": "Technical Story",
                "summary": f"Story {key}",
                "description": "",
                "acceptance_criteria": "",
            }
        ],
    }


def _mock_jira(monkeypatch, by_key: dict[str, dict | None]) -> None:
    monkeypatch.setattr("app.services.epc_paste._require_config", lambda: ("http://jira", "e", "t"))

    def fake_fetch(keys: list[str]) -> list[dict]:
        found = []
        for key in keys:
            row = by_key.get(key.upper())
            if row:
                found.append(row)
        return found

    monkeypatch.setattr("app.services.epc_paste.fetch_artifacts_for_keys", fake_fetch)


def test_parse_adt_three_epcs() -> None:
    parsed = parse_epc_paste(
        "Dispositivo ADT\nADTCL-2394\nADTCL-2323\nADTCL-541\n"
    )
    assert [item.key for item in parsed.items] == ["ADTCL-2394", "ADTCL-2323", "ADTCL-541"]
    assert parsed.devices == ["ADT"]
    assert parsed.duplicates == []
    assert parsed.invalid_lines == []


def test_parse_adt_and_win_keeps_grouping() -> None:
    parsed = parse_epc_paste(
        "Dispositivo ADT\nADTCL-2394\n\nDispositivo WIN\nWINCL-219\n"
    )
    assert [item.key for item in parsed.items] == ["ADTCL-2394", "WINCL-219"]
    assert parsed.devices == ["ADT", "WIN"]
    assert parsed.items[0].device_heading == "ADT"
    assert parsed.items[1].device_heading == "WIN"


def test_parse_duplicate_keeps_first() -> None:
    parsed = parse_epc_paste("ADTCL-2394\nADTCL-2394\n")
    assert [item.key for item in parsed.items] == ["ADTCL-2394"]
    assert parsed.duplicates == ["ADTCL-2394"]


def test_parse_invalid_text_is_not_an_epic() -> None:
    parsed = parse_epc_paste("Dispositivo ADT\nTEXTO_INVALIDO\n")
    assert parsed.items == []
    assert parsed.invalid_lines == ["TEXTO_INVALIDO"]


def test_parse_inconsistent_device_does_not_reassign() -> None:
    parsed = parse_epc_paste("Dispositivo ADT\nWINCL-219\n")
    assert parsed.items[0].key == "WINCL-219"
    assert parsed.items[0].device_heading == "ADT"
    assert parsed.mismatches == [{"key": "WINCL-219", "heading": "ADT", "prefix": "WINCL"}]


def test_analyze_rn_pdf_unchanged(client, monkeypatch, tmp_path) -> None:
    from app.config import settings
    from dataclasses import replace

    monkeypatch.setattr(
        "app.services.rn_storage.settings",
        replace(settings, rn_storage_dir=str(tmp_path)),
    )
    response = client.post(
        "/api/v1/releases/analyze-rn",
        files={"file": (WEB_RN.name, WEB_RN.read_bytes(), "application/pdf")},
    )
    assert response.status_code == 200
    analysis = response.json()["analysis"]
    assert analysis["pdf_file_path"]
    assert analysis["raw_analysis"].get("source") != "pasted_epcs"
    assert analysis["features_count"] == 5
    assert Path(analysis["pdf_file_path"]).is_file()


def test_analyze_epcs_adt_list(client, monkeypatch) -> None:
    _mock_jira(
        monkeypatch,
        {
            "ADTCL-2394": _artifact("ADTCL-2394"),
            "ADTCL-2323": _artifact("ADTCL-2323"),
            "ADTCL-541": _artifact("ADTCL-541"),
        },
    )
    response = client.post(
        "/api/v1/releases/analyze-epcs",
        json={"text": "Dispositivo ADT\nADTCL-2394\nADTCL-2323\nADTCL-541\n"},
    )
    assert response.status_code == 200
    analysis = response.json()["analysis"]
    assert analysis["pdf_file_path"] is None
    assert analysis["raw_analysis"]["source"] == "pasted_epcs"
    epics = analysis["raw_analysis"]["normalized"]["technical_epics"]
    assert [row["id"] for row in epics] == ["ADTCL-2394", "ADTCL-2323", "ADTCL-541"]
    assert all(row["title"] == f"Summary {row['id']}" for row in epics)
    assert analysis["features_count"] == 3
    assert analysis["nco_issues_count"] == 0
    assert analysis["qa_qc_issues_count"] == 0
    assert analysis["tri_issues_count"] == 0
    assert analysis["detected_platform"] == "ADT"
    assert analysis["raw_analysis"]["epc_paste"]["devices"] == ["ADT"]


def test_analyze_epcs_adt_and_win_does_not_pick_first_platform(client, monkeypatch) -> None:
    _mock_jira(
        monkeypatch,
        {
            "ADTCL-2394": _artifact("ADTCL-2394"),
            "WINCL-219": _artifact("WINCL-219"),
        },
    )
    response = client.post(
        "/api/v1/releases/analyze-epcs",
        json={"text": "Dispositivo ADT\nADTCL-2394\n\nDispositivo WIN\nWINCL-219\n"},
    )
    analysis = response.json()["analysis"]
    assert analysis["detected_platform"] is None
    assert analysis["detected_devices"] == "ADT, WIN"
    assert analysis["features_count"] == 2
    grouped = analysis["raw_analysis"]["epc_paste"]["grouped"]
    assert grouped == [
        {"device": "ADT", "keys": ["ADTCL-2394"]},
        {"device": "WIN", "keys": ["WINCL-219"]},
    ]
    assert any("no se eligió automáticamente" in row for row in analysis["observations"])


def test_analyze_epcs_duplicate(client, monkeypatch) -> None:
    _mock_jira(monkeypatch, {"ADTCL-2394": _artifact("ADTCL-2394")})
    analysis = client.post(
        "/api/v1/releases/analyze-epcs",
        json={"text": "ADTCL-2394\nADTCL-2394\n"},
    ).json()["analysis"]
    epics = analysis["raw_analysis"]["normalized"]["technical_epics"]
    assert [row["id"] for row in epics] == ["ADTCL-2394"]
    assert any("duplicado" in row.lower() for row in analysis["observations"])


def test_analyze_epcs_invalid_text(client, monkeypatch) -> None:
    _mock_jira(monkeypatch, {})
    analysis = client.post(
        "/api/v1/releases/analyze-epcs",
        json={"text": "Dispositivo ADT\nTEXTO_INVALIDO\n"},
    ).json()["analysis"]
    assert analysis["raw_analysis"]["normalized"]["technical_epics"] == []
    assert analysis["features_count"] == 0
    assert any("TEXTO_INVALIDO" in row for row in analysis["observations"])


def test_analyze_epcs_missing_in_jira(client, monkeypatch) -> None:
    _mock_jira(monkeypatch, {})
    analysis = client.post(
        "/api/v1/releases/analyze-epcs",
        json={"text": "ADTCL-999999\n"},
    ).json()["analysis"]
    epic = analysis["raw_analysis"]["normalized"]["technical_epics"][0]
    assert epic["id"] == "ADTCL-999999"
    assert epic["title"] is None
    assert any("No encontrado en Jira" in row for row in analysis["observations"])


def test_analyze_epcs_inconsistent_device_warning(client, monkeypatch) -> None:
    _mock_jira(monkeypatch, {"WINCL-219": _artifact("WINCL-219")})
    analysis = client.post(
        "/api/v1/releases/analyze-epcs",
        json={"text": "Dispositivo ADT\nWINCL-219\n"},
    ).json()["analysis"]
    epic = analysis["raw_analysis"]["normalized"]["technical_epics"][0]
    assert epic["id"] == "WINCL-219"
    assert epic["device_heading"] == "ADT"
    assert any("no se reasignó" in row for row in analysis["observations"])


def test_analyze_epcs_does_not_write_operativa_epc(client, monkeypatch, db_session) -> None:
    _mock_jira(monkeypatch, {"ADTCL-2394": _artifact("ADTCL-2394")})
    client.post("/api/v1/releases/analyze-epcs", json={"text": "ADTCL-2394"})
    rows = db_session.execute(select(Epc)).scalars().all()
    assert rows == []


def test_operativa_analyze_rn_still_independent(client) -> None:
    response = client.post(
        "/api/v1/operativa/analyze-rn",
        files={"file": ("notas.txt", b"hola", "text/plain")},
    )
    assert response.status_code == 400


def test_generate_from_pasted_epcs_skips_pdf_and_uses_jira_artifacts(
    client, monkeypatch
) -> None:
    from dataclasses import replace

    from app.config import settings

    monkeypatch.setattr(
        "app.services.ai_case_engine.settings",
        replace(settings, openai_api_key=""),
    )
    _mock_jira(monkeypatch, {"ADTCL-2394": _artifact("ADTCL-2394")})
    analyzed = client.post(
        "/api/v1/releases/analyze-epcs",
        json={"text": "Dispositivo ADT\nADTCL-2394\n"},
    )
    analysis = analyzed.json()["analysis"]
    created = client.post(
        "/api/v1/releases",
        json={
            "name": "Pasted EPCs",
            "version": "1.0.0",
            "platform": "ADT",
            "analysis_data": analysis,
        },
    )
    assert created.status_code == 201
    release_id = created.json()["id"]

    fetched_keys: list[list[str]] = []

    def fake_fetch(keys: list[str]) -> list[dict]:
        fetched_keys.append([str(key).upper() for key in keys])
        desc = (
            "Feature: ADTCL-2394\n"
            "Scenario: Completar el flujo\n"
            "  When el usuario selecciona pagar\n"
            "  Then se muestra el modal de confirmación y el usuario ve el resultado\n"
        )
        return [
            {
                "key": "ADTCL-2394",
                "issuetype": "Technical Epic",
                "summary": "Feature ADTCL-2394",
                "description": desc,
                "acceptance_criteria": "El usuario ve el resultado",
                "children": [
                    {
                        "key": "ADTCL-2394",
                        "issuetype": "Story",
                        "summary": "Feature ADTCL-2394",
                        "description": desc,
                        "acceptance_criteria": "El usuario ve el resultado",
                    }
                ],
            }
        ]

    def boom_pdf(*_args, **_kwargs):
        raise AssertionError("generate-cases must not parse a PDF for pasted_epcs")

    monkeypatch.setattr("app.services.ai_case_engine.fetch_artifacts_for_keys", fake_fetch)
    monkeypatch.setattr("app.routers.releases._tickets_by_section", boom_pdf)
    monkeypatch.setattr("app.services.ai_case_engine._tickets_by_section", boom_pdf)
    monkeypatch.setattr(RuleBasedPdfAnalyzer, "analyze", boom_pdf)

    response = client.post(f"/api/v1/releases/{release_id}/generate-cases")
    assert response.status_code == 200, response.text
    body = response.json()
    assert fetched_keys
    assert "ADTCL-2394" in fetched_keys[0]
    assert body["has_analysis"] is True
    assert body["engine"] in {"evidence", "evidence-jira"}


def test_tickets_from_normalized_preserves_full_keys() -> None:
    raw = {
        "source": "pasted_epcs",
        "normalized": {
            "technical_epics": [
                {"id": "ADTCL-2394", "title": "Summary ADTCL-2394"},
                {"id": "WINCL-219", "title": None},
            ]
        },
    }
    tickets = tickets_from_normalized_technical_epics(raw)
    assert tickets["functionality"] == [
        ("ADTCL-2394", "Summary ADTCL-2394"),
        ("WINCL-219", "WINCL-219"),
    ]
    assert tickets["nco"] == []
