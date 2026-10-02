from io import BytesIO

from openpyxl import load_workbook

from app.services.rn_scope_export import SCOPE_HEADERS, build_rn_scope_workbook, extract_rn_scope_rows
from tests.test_case_generation import WEB_RN, _create_app_release_with_rn, _store_dir

_WEB_FEATURES = {"WEBCL-3721", "WEBCL-3153", "WEBCL-3779", "WEBCL-3762", "WEBCL-3767"}


def test_extract_web_rn_scope_without_jira() -> None:
    rows = extract_rn_scope_rows(WEB_RN.read_bytes(), fetch_jira=False)
    keys = {row["key"] for row in rows}
    assert _WEB_FEATURES <= keys
    epics = [row for row in rows if row["actividad"] == "Technical Epic"]
    assert {row["key"] for row in epics} >= _WEB_FEATURES
    assert all(row["descripcion"] for row in epics)
    assert {row["actividad"] for row in rows} <= {
        "Technical Epic",
        "NCO",
        "QA Bug",
        "QC Bug",
        "QA/QC Bug",
        "TRI",
    }


def test_extract_splits_qa_qc_from_jira_issuetype(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.rn_scope_export.iter_rn_ticket_rows",
        lambda _pdf: [
            ("WEBCL-3849", "WEBCL-3849: login fallido", "qa_qc"),
            ("WEBCL-3900", "WEBCL-3900: crash al pagar", "qa_qc"),
            ("WEBCL-3721", "WEBCL-3721: TE-activacion", "functionality"),
        ],
    )
    fields = {
        "WEBCL-3849": {
            "issuetype": "QA Bug",
            "priority": "High",
            "status": "Done",
            "affected_versions": "16.9.0",
            "fix_versions": "16.9.1",
        },
        "WEBCL-3900": {
            "issuetype": "QC Bug",
            "priority": "Highest",
            "status": "In Progress",
            "affected_versions": "",
            "fix_versions": "16.9.1",
        },
    }
    by_key = {
        row["key"]: row
        for row in extract_rn_scope_rows(b"pdf", jira_fields=fields, fetch_jira=False)
    }
    assert by_key["WEBCL-3849"]["actividad"] == "QA Bug"
    assert by_key["WEBCL-3849"]["prioridad"] == "High"
    assert by_key["WEBCL-3849"]["estado"] == "Done"
    assert by_key["WEBCL-3849"]["version_afectada"] == "16.9.0"
    assert by_key["WEBCL-3849"]["version_correctora"] == "16.9.1"
    assert by_key["WEBCL-3900"]["actividad"] == "QC Bug"
    assert by_key["WEBCL-3721"]["actividad"] == "Technical Epic"


def test_workbook_headers_and_rows() -> None:
    payload = build_rn_scope_workbook(WEB_RN.read_bytes(), fetch_jira=False)
    book = load_workbook(BytesIO(payload))
    sheet = book.active
    assert [cell.value for cell in sheet[1]] == SCOPE_HEADERS
    assert sheet.max_row > 1
    assert sheet["A2"].value


def test_export_rn_scope_from_release(client, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("app.services.rn_scope_export.fetch_scope_fields_for_keys", lambda _keys: {})
    release_id, _analysis = _create_app_release_with_rn(client, monkeypatch, tmp_path)
    response = client.get(f"/api/v1/releases/{release_id}/rn-scope/export")
    assert response.status_code == 200, response.text
    assert "spreadsheet" in response.headers["content-type"]
    book = load_workbook(BytesIO(response.content))
    keys = {row[0] for row in book.active.iter_rows(min_row=2, values_only=True)}
    assert _WEB_FEATURES <= keys


def test_export_rn_scope_from_analyzed_pdf(client, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("app.services.rn_scope_export.fetch_scope_fields_for_keys", lambda _keys: {})
    _store_dir(monkeypatch, tmp_path)
    analyzed = client.post(
        "/api/v1/releases/analyze-rn",
        files={"file": (WEB_RN.name, WEB_RN.read_bytes(), "application/pdf")},
    )
    assert analyzed.status_code == 200
    path = analyzed.json()["analysis"]["pdf_file_path"]
    response = client.post(
        "/api/v1/releases/rn-scope/export",
        json={"pdf_file_path": path, "filename": WEB_RN.name},
    )
    assert response.status_code == 200, response.text
    assert "spreadsheet" in response.headers["content-type"]


def test_export_rn_scope_rejects_path_outside_storage(client, monkeypatch, tmp_path) -> None:
    _store_dir(monkeypatch, tmp_path)
    response = client.post(
        "/api/v1/releases/rn-scope/export",
        json={"pdf_file_path": str(WEB_RN)},
    )
    assert response.status_code == 404
