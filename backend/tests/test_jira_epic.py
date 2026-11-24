"""QCO Epic from a release. No live Jira."""

import httpx
import pytest

from app.services.jira_epic import (
    EpicDraft,
    JiraEpicError,
    VersionScope,
    _adf,
    accumulated_description,
    assignee_for,
    cycle_title,
    epic_description,
    epic_summary,
    program_code,
    publish_epic,
)


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
    assert "- TVOSPR-255" in text
    assert "Integración" not in text
    assert "QA Validation" not in text
    assert "- TVOSPR-804" in text
    assert "Tipografía" not in text
    assert "Listado de QA/QC Bugs" in text
    assert "Tipo de prueba: Regresión completa" in text
    assert "RN: RN.pdf\n\nAmbiente: BERC\n\nVersión: vTVOS-10.13.1" in text
    doc = _adf("Objetivo\n\n- TVOSPR-255\n- TVOSPR-28")
    assert doc["content"][0]["content"][0]["marks"] == [{"type": "strong"}]
    cards = doc["content"][2]["content"]
    assert cards[0]["content"][0]["content"][0]["type"] == "inlineCard"
    assert cards[0]["content"][0]["content"][0]["attrs"]["url"].endswith("/browse/TVOSPR-255")
    assert cards[1]["content"][0]["content"][0]["attrs"]["url"].endswith("/browse/TVOSPR-28")


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
    assert "- WEBCL-12" in text
    assert "Guía" not in text


def test_unknown_program_is_rejected() -> None:
    with pytest.raises(JiraEpicError):
        program_code("Kepler")


def _scope(
    release_id: int,
    version: str,
    functionalities: tuple[tuple[str, str], ...],
    bugs: tuple[tuple[str, str], ...] = (),
) -> VersionScope:
    return VersionScope(
        release_id=release_id,
        version=version,
        device="tvOS",
        environment="BERC",
        validation_type="Regresión completa",
        rn_filename="RN.pdf",
        activity_type="Release",
        functionalities=functionalities,
        qc_bugs=bugs,
    )


def test_revalidation_renames_the_epic_and_keeps_only_the_new_scope() -> None:
    first = _scope(1, "vTVOS-10.13.1", (("TVOSPR-255", "pegado"), ("TVOSPR-28", "")), (("TVOSPR-1992", ""),))
    second = _scope(2, "vTVOS-10.13.2", (("TVOSPR-255", ""), ("TVOSPR-2100", "")), (("TVOSPR-1992", ""), ("TVOSPR-2108", "")))
    text = accumulated_description([first, second])
    assert cycle_title("TVOSPR", ["vTVOS-10.13.1", "vTVOS-10.13.2"], "Release") == (
        "TVOSPR | Ciclo1: vTVOS-10.13.1 Ciclo2: vTVOS-10.13.2 | RELEASE"
    )
    assert text.index("Tipo de prueba: Regresión completa") < text.index("Nuevo alcance en la versión vTVOS-10.13.2")
    assert text.index("Nuevo alcance en la versión vTVOS-10.13.2") < text.index("Otra información")
    assert "- TVOSPR-2100" in text
    assert "- TVOSPR-2108" in text
    assert text.count("TVOSPR-255") == 1
    assert text.count("TVOSPR-1992") == 1
    assert "pegado" not in text
    assert "RN: RN.pdf\n\nAmbiente: BERC\n\nVersión: vTVOS-10.13.1" in text

    empty_delta = accumulated_description([first, _scope(2, "vTVOS-10.13.2", (("TVOSPR-255", ""),), (("TVOSPR-1992", ""),))])
    assert "Nuevo alcance en la versión vTVOS-10.13.2" in empty_delta
    assert empty_delta.count("Listado de EPCs") == 1
    assert empty_delta.count("Listado de QA/QC Bugs") == 1
    assert "Tipo de regresión: Regresión completa" in empty_delta


def test_publish_creates_one_epic_and_one_task(monkeypatch) -> None:
    draft = EpicDraft(
        release_id=4,
        summary="WEBCL | 16.11.3 | HOTFIX",
        description="Objetivo",
        activity_type="HotFix",
        environment="FEHF",
        assignee_id="60be5d2ba01e11006ab15146",
    )
    store: dict[str, dict] = {}

    def search(jql: str, limit: int = 5, fields: list[str] | None = None):
        del limit, fields
        if "Epic" in jql and "QCO-1" in store:
            return [{"key": "QCO-1", "fields": {"summary": draft.summary, "labels": ["qcpulse-r4"]}}]
        if "Tarea" in jql and draft.summary in jql and "QCO-2" in store:
            return [{"key": "QCO-2", "fields": {"labels": ["qcpulse-r4"]}}]
        return []

    def create(fields: dict):
        key = "QCO-1" if fields["issuetype"]["name"] == "Epic" else "QCO-2"
        store[key] = fields
        return key

    updated: list[str] = []
    monkeypatch.setattr("app.services.jira_epic._search", search)
    monkeypatch.setattr("app.services.jira_epic._create_issue", create)
    monkeypatch.setattr("app.services.jira_epic._account_id", lambda: None)
    monkeypatch.setattr("app.services.jira_epic._put_fields", lambda key, _fields: updated.append(key))
    monkeypatch.setattr("app.services.jira_epic._read_labels", lambda _key: ["qcpulse"])

    first = publish_epic(draft)
    second = publish_epic(draft)

    assert first.already_existed is False
    assert first.key == "QCO-1"
    assert first.task_key == "QCO-2"
    assert first.task_already_existed is False
    assert store["QCO-1"]["priority"] == {"id": "3"}
    assert store["QCO-1"]["assignee"] == {"accountId": "60be5d2ba01e11006ab15146"}
    assert store["QCO-1"]["issuetype"] == {"name": "Epic"}
    assert store["QCO-2"]["issuetype"] == {"name": "Tarea"}
    assert store["QCO-2"]["parent"] == {"key": "QCO-1"}
    assert store["QCO-2"]["assignee"] == store["QCO-1"]["assignee"]
    assert store["QCO-2"]["summary"] == draft.summary
    assert second.already_existed is True
    assert second.task_already_existed is True
    assert updated == ["QCO-1", "QCO-2"]
    assert len(store) == 2


def test_revalidation_adds_the_new_task_under_the_same_epic(monkeypatch) -> None:
    scopes = (
        _scope(1, "vTVOS-10.13.1", (("TVOSPR-255", ""),), (("TVOSPR-1992", ""),)),
        _scope(2, "vTVOS-10.13.2", (("TVOSPR-255", ""), ("TVOSPR-2100", "")), (("TVOSPR-2108", ""),)),
        _scope(3, "vTVOS-10.13.3", (("TVOSPR-2200", ""),)),
    )
    draft = EpicDraft(
        release_id=2,
        summary="TVOSPR | vTVOS-10.13.2 | RELEASE",
        description="tarea",
        activity_type="Release",
        environment="BERC",
        assignee_id="5f6a0720f0d4010070378042",
        deliverable_id=9,
        program="TVOSPR",
        scopes=scopes,
    )
    created: list[dict] = []
    updated: list[tuple[str, dict]] = []
    attached: list[str] = []

    def search(jql: str, limit: int = 5, fields: list[str] | None = None):
        del limit, fields
        if "Epic" in jql:
            return [{"key": "QCO-49805", "fields": {"labels": ["qcpulse-r1"]}}]
        if "Tarea" in jql and "labels in" in jql:
            return [{"key": "QCO-8", "fields": {"labels": ["qcpulse", "qcpulse-r3"]}}]
        return []

    monkeypatch.setattr("app.services.jira_epic._search", search)
    monkeypatch.setattr("app.services.jira_epic._create_issue", lambda fields: created.append(fields) or "QCO-9")
    monkeypatch.setattr("app.services.jira_epic._account_id", lambda: None)
    monkeypatch.setattr("app.services.jira_epic._put_fields", lambda key, fields: updated.append((key, fields)))
    monkeypatch.setattr("app.services.jira_epic._read_labels", lambda _key: ["qcpulse", "qcpulse-r1"])
    monkeypatch.setattr("app.services.jira_epic._attach_release_note", lambda key, _draft: attached.append(key))

    result = publish_epic(draft)

    assert result.already_existed is True
    assert result.key == "QCO-49805"
    assert result.summary == "TVOSPR | Ciclo1: vTVOS-10.13.1 Ciclo2: vTVOS-10.13.2 Ciclo3: vTVOS-10.13.3 | RELEASE"
    assert result.task_key == "QCO-9"
    assert result.task_summary == "TVOSPR | vTVOS-10.13.2 | RELEASE"
    assert result.task_already_existed is False
    assert len(created) == 1
    assert created[0]["issuetype"] == {"name": "Tarea"}
    assert created[0]["parent"] == {"key": "QCO-49805"}
    assert created[0]["assignee"] == {"accountId": "5f6a0720f0d4010070378042"}
    assert created[0]["summary"] == "TVOSPR | vTVOS-10.13.2 | RELEASE"
    assert updated[0][0] == "QCO-49805"
    assert updated[0][1]["summary"] == result.summary
    assert "qcpulse-d9" in updated[0][1]["labels"]
    assert attached == ["QCO-49805", "QCO-9"]


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
