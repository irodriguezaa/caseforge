"""QCO Epic from a release. No live Jira."""

import httpx
import pytest

from app.services.jira_epic import JiraEpicError, _adf, assignee_for, epic_description, epic_summary, program_code, publish_epic
from app.services.jira_epic import EpicDraft


def test_summary_uses_program_version_and_type() -> None:
    assert program_code("WEB") == "WEBCL"
    assert program_code("AAF Evolutivo") == "STVCL"
    assert program_code("FireTV") == "ADTCL"
    assert program_code("Roku") == "ROKUPR"
    assert program_code("STV Tata LG") == "SCTCL"
    assert program_code("IPTV AOSP") == "AOSPCL"
    assert program_code("tvOS") == "TVOSPR"
    assert assignee_for("ROKUPR") == assignee_for("ATSCL")
    assert epic_summary("TVOSPR", "vTVOS-10.13.1", "Exc") == "TVOSPR | vTVOS-10.13.1 | EXC"
    text = epic_description(
        device="tvOS",
        version="vTVOS-10.13.1",
        environment="BERC",
        validation_type="Regresión completa",
        rn_filename="RN.pdf",
        functionalities=[("TVOSPR-255", "TVOSPR-255: Integración de landingQA Validation")],
        qc_bugs=[("TVOSPR-804", "TVOSPR-804: TipografíaDone")],
    )
    assert "Liberar tvOS versión vTVOS-10.13.1 para Claro Video" in text
    assert "Clarovideo tvOS." in text
    assert "entorno BERC." in text
    assert "- TVOSPR-255 Integración de landing" in text
    assert "QA Validation" not in text
    assert "- TVOSPR-804 Tipografía" in text
    assert "Done" not in text
    assert "Listado de QA/QC Bugs" in text
    assert "Tipo de prueba: Regresión completa" in text
    assert "RN: RN.pdf\n\nAmbiente: BERC\n\nVersión: vTVOS-10.13.1" in text
    heading = _adf("Objetivo\n\nLiberar")["content"][0]
    assert heading["content"][0]["marks"] == [{"type": "strong"}]


def test_empty_bug_list_is_omitted() -> None:
    text = epic_description(
        device="WEB",
        version="16.11.3",
        environment="FEHF",
        validation_type="Regresivo",
        rn_filename="RN.pdf",
        functionalities=[("WEBCL-12", "Guía")],
        qc_bugs=[],
    )
    assert "QA/QC Bugs" not in text
    assert "- WEBCL-12 Guía" in text


def test_unknown_program_is_rejected() -> None:
    with pytest.raises(JiraEpicError):
        program_code("Kepler")


def test_publish_creates_one_epic_and_reuses_it(monkeypatch) -> None:
    draft = EpicDraft(
        release_id=4,
        summary="WEBCL | 16.11.3 | HOTFIX",
        description="Objetivo",
        activity_type="HotFix",
        environment="FEHF",
        assignee_id="60be5d2ba01e11006ab15146",
    )
    store: dict[str, dict] = {}

    def search(jql: str):
        if draft.summary in jql and store:
            return [{"key": next(iter(store))}]
        return []

    def create(fields: dict):
        store["QCO-1"] = fields
        return "QCO-1"

    monkeypatch.setattr("app.services.jira_epic._search", search)
    monkeypatch.setattr("app.services.jira_epic._create_issue", create)
    monkeypatch.setattr("app.services.jira_epic._account_id", lambda: None)

    first = publish_epic(draft)
    second = publish_epic(draft)

    assert first.already_existed is False
    assert first.key == "QCO-1"
    assert store["QCO-1"]["priority"] == {"id": "3"}
    assert store["QCO-1"]["assignee"] == {"accountId": "60be5d2ba01e11006ab15146"}
    assert store["QCO-1"]["issuetype"] == {"name": "Epic"}
    assert second.already_existed is True
    assert len(store) == 1


def test_pdf_upload_is_multipart() -> None:
    client = httpx.Client(headers={"Accept": "application/json", "X-Atlassian-Token": "no-check"})
    request = client.build_request(
        "POST",
        "https://example.test/rest/api/3/issue/QCO-49805/attachments",
        files={"file": ("RN.pdf", b"%PDF", "application/pdf")},
    )
    assert request.headers["content-type"].startswith("multipart/form-data")


def test_route_requires_cases(client) -> None:
    created = client.post(
        "/api/v1/releases",
        json={
            "name": "CV WEB",
            "version": "16.11.3",
            "platform": "WEB",
            "activity_type": "HotFix",
            "environment": "FEHF",
        },
    )
    assert created.status_code == 201
    assert created.json()["activity_type"] == "HotFix"
    assert created.json()["environment"] == "FEHF"

    response = client.post(
        f"/api/v1/releases/{created.json()['id']}/jira-epic",
        json={"activity_type": "HotFix", "environment": "FEHF"},
    )
    assert response.status_code == 400
    assert "casos" in response.json()["detail"]
