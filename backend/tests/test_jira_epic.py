"""QCO Epic from a release. No live Jira."""

import httpx
import pytest

from app.services.jira_epic import (
    EpicDraft,
    JiraEpicError,
    SprintChoice,
    VersionScope,
    _adf,
    _move_issues_to_sprint,
    _sprint_choice,
    accumulated_description,
    assignee_for,
    cycle_title,
    epic_description,
    epic_summary,
    program_code,
    publish_epic,
    subtasks_for,
    task_description,
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


def test_later_version_task_lists_only_the_new_scope() -> None:
    first = _scope(1, "vWINCL-11.1.0", (("WINCL-528", ""), ("WINCL-2237", "")), (("WINCL-2358", ""),))
    second = _scope(
        2,
        "vWINCL-11.1.1",
        (("WINCL-528", ""), ("WINCL-2237", "")),
        (("WINCL-2358", ""), ("WINCL-2520", "")),
    )
    text = task_description([first, second], second)
    assert "Liberar tvOS versión vWINCL-11.1.1 para Claro Video" in text
    assert "Listado de EPCs (funcionalidades)\nNo hay nuevas funcionalidades" in text
    assert "Listado de QA/QC Bugs\n- WINCL-2520" in text
    assert "WINCL-528" not in text
    assert "WINCL-2237" not in text
    assert "WINCL-2358" not in text
    assert "Versión: vWINCL-11.1.1" in text
    assert "Nuevo alcance" not in text

    opening = task_description([first, second], first)
    assert "- WINCL-528" in opening
    assert "- WINCL-2237" in opening
    assert "No hay nuevas funcionalidades" not in opening

    with_feature = task_description(
        [first, _scope(2, "vWINCL-11.1.1", (("WINCL-528", ""), ("WINCL-2600", "")), ())],
        _scope(2, "vWINCL-11.1.1", (("WINCL-528", ""), ("WINCL-2600", "")), ()),
    )
    assert "- WINCL-2600" in with_feature
    assert "WINCL-528" not in with_feature
    assert "No hay nuevas funcionalidades" not in with_feature
    assert "QA/QC Bugs" not in with_feature


def test_subtasks_follow_the_same_scope_as_the_task() -> None:
    first = _scope(1, "vWINCL-11.1.0", (("WINCL-528", ""), ("WINCL-2237", "")), (("WINCL-2358", ""),))
    second = _scope(
        2,
        "vWINCL-11.1.1",
        (("WINCL-528", ""), ("WINCL-2237", "")),
        (("WINCL-2358", ""), ("WINCL-2520", "")),
    )
    opening = subtasks_for("WINCL", [first, second], first)
    assert [row.summary for row in opening] == [
        "WINCL | vWINCL-11.1.0 | WINCL-528",
        "WINCL | vWINCL-11.1.0 | WINCL-2237",
        "WINCL | vWINCL-11.1.0 | Revisión QC Bugs",
        "WINCL | vWINCL-11.1.0 | REGRESIÓN",
    ]
    assert opening[0].description == "Validación funcional de WINCL-528 con la versión vWINCL-11.1.0"
    assert "WINCL-2358" in opening[2].description
    assert opening[3].description == "Regresión completa"

    later = subtasks_for("WINCL", [first, second], second)
    assert [row.summary for row in later] == [
        "WINCL | vWINCL-11.1.1 | Revisión QC Bugs",
        "WINCL | vWINCL-11.1.1 | REGRESIÓN",
    ]
    assert "WINCL-2520" in later[0].description
    assert "WINCL-2358" not in later[0].description
    assert "WINCL-528" not in later[0].description

    no_bugs = subtasks_for("WINCL", [first, _scope(2, "vWINCL-11.1.1", (("WINCL-2600", ""),), ())], _scope(2, "vWINCL-11.1.1", (("WINCL-2600", ""),), ()))
    assert [row.summary for row in no_bugs] == [
        "WINCL | vWINCL-11.1.1 | WINCL-2600",
        "WINCL | vWINCL-11.1.1 | REGRESIÓN",
    ]


def _plain(node: object) -> str:
    if isinstance(node, dict):
        parts = [str(node.get("text") or ""), str((node.get("attrs") or {}).get("url") or "")]
        parts.extend(_plain(child) for child in node.get("content") or [])
        return " ".join(part for part in parts if part)
    if isinstance(node, list):
        return " ".join(_plain(child) for child in node)
    return ""


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
    keys = iter(["QCO-9", "QCO-10", "QCO-11", "QCO-12"])
    monkeypatch.setattr("app.services.jira_epic._create_issue", lambda fields: created.append(fields) or next(keys))
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
    assert result.subtask_count == 3
    assert result.subtasks_already_existed == 0
    assert len(created) == 4
    assert created[0]["issuetype"] == {"name": "Tarea"}
    assert created[0]["parent"] == {"key": "QCO-49805"}
    assert created[0]["assignee"] == {"accountId": "5f6a0720f0d4010070378042"}
    assert created[0]["summary"] == "TVOSPR | vTVOS-10.13.2 | RELEASE"
    description = _plain(created[0]["description"])
    assert "No hay nuevas funcionalidades" not in description
    assert "TVOSPR-2100" in description
    assert "TVOSPR-2108" in description
    assert "TVOSPR-255" not in description
    assert [row["summary"] for row in created[1:]] == [
        "TVOSPR | vTVOS-10.13.2 | TVOSPR-2100",
        "TVOSPR | vTVOS-10.13.2 | Revisión QC Bugs",
        "TVOSPR | vTVOS-10.13.2 | REGRESIÓN",
    ]
    assert all(row["issuetype"] == {"name": "Subtarea"} for row in created[1:])
    assert all(row["parent"] == {"key": "QCO-9"} for row in created[1:])
    assert all(row["assignee"] == {"accountId": "5f6a0720f0d4010070378042"} for row in created[1:])
    assert created[1]["description"]["content"][0]["content"][0]["text"] == (
        "Validación funcional de TVOSPR-2100 con la versión vTVOS-10.13.2"
    )
    assert "TVOSPR-2108" in _plain(created[2]["description"])
    assert "TVOSPR-255" not in _plain(created[2]["description"])
    assert _plain(created[3]["description"]) == "Regresión completa"
    assert updated[0][0] == "QCO-49805"
    assert updated[0][1]["summary"] == result.summary
    assert "qcpulse-d9" in updated[0][1]["labels"]
    assert attached == ["QCO-49805", "QCO-9"]


def test_second_click_updates_subtasks_without_duplicating(monkeypatch) -> None:
    scopes = (
        _scope(1, "vWINCL-11.1.0", (("WINCL-528", ""),), (("WINCL-2358", ""),)),
        _scope(2, "vWINCL-11.1.1", (("WINCL-528", ""),), (("WINCL-2358", ""), ("WINCL-2520", ""))),
    )
    draft = EpicDraft(
        release_id=2,
        summary="WINCL | vWINCL-11.1.1 | RELEASE",
        description="tarea",
        activity_type="Release",
        environment="PROD",
        assignee_id="60be5d2ba01e11006ab15146",
        deliverable_id=4,
        program="WINCL",
        scopes=scopes,
    )
    created: list[dict] = []

    def search(jql: str, limit: int = 5, fields: list[str] | None = None):
        del limit, fields
        if "Epic" in jql:
            return [{"key": "QCO-1", "fields": {"labels": ["qcpulse-r1"]}}]
        if "Subtarea" in jql and "Revisión QC Bugs" in jql:
            return [{"key": "QCO-21"}]
        if "Subtarea" in jql and "REGRESIÓN" in jql:
            return [{"key": "QCO-22"}]
        if "issuetype = \"Tarea\"" in jql and "summary" in jql:
            return [{"key": "QCO-9"}]
        if "labels in" in jql:
            return [{"key": "QCO-9", "fields": {"labels": ["qcpulse-r2"]}}]
        return []

    monkeypatch.setattr("app.services.jira_epic._search", search)
    monkeypatch.setattr("app.services.jira_epic._create_issue", lambda fields: created.append(fields) or "QCO-99")
    monkeypatch.setattr("app.services.jira_epic._account_id", lambda: None)
    monkeypatch.setattr("app.services.jira_epic._put_fields", lambda _key, _fields: None)
    monkeypatch.setattr("app.services.jira_epic._read_labels", lambda _key: ["qcpulse"])
    monkeypatch.setattr("app.services.jira_epic._attach_release_note", lambda _key, _draft: None)

    result = publish_epic(draft)

    assert created == []
    assert result.task_already_existed is True
    assert result.subtask_count == 2
    assert result.subtasks_already_existed == 2


def test_qc_sprint_label_uses_the_board_dates() -> None:
    sprint_49 = _sprint_choice(
        {
            "id": 27623,
            "name": "Sprint 49",
            "state": "future",
            "startDate": "2026-11-16T06:00:00.000Z",
            "endDate": "2026-11-27T06:00:00.000Z",
        }
    )
    sprint_50 = _sprint_choice(
        {
            "id": 27624,
            "name": "Sprint 50",
            "state": "future",
            "startDate": "2026-11-30T06:00:00.000Z",
            "endDate": "2026-12-11T06:00:00.000Z",
        }
    )
    assert sprint_49 is not None and sprint_49.label == "Sprint 49 · 16 nov – 27 nov"
    assert sprint_50 is not None and sprint_50.label == "Sprint 50 · 30 nov – 11 dic"
    assert _sprint_choice({"id": 1, "name": "Sprint 47", "state": "closed"}) is None


def test_publish_moves_epic_task_and_subtasks_to_the_chosen_sprint(monkeypatch) -> None:
    draft = EpicDraft(
        release_id=2,
        summary="WINCL | vWINCL-11.1.1 | RELEASE",
        description="tarea",
        activity_type="Release",
        environment="PROD",
        assignee_id="60be5d2ba01e11006ab15146",
        deliverable_id=4,
        program="WINCL",
        scopes=(_scope(2, "vWINCL-11.1.1", (("WINCL-528", ""),), (("WINCL-2520", ""),)),),
    )
    keys = iter(["QCO-1", "QCO-2", "QCO-3", "QCO-4", "QCO-5"])
    moved: list[tuple[int, list[str]]] = []
    sprint = SprintChoice(id=27623, name="Sprint 49", state="future", label="Sprint 49 · 16 nov – 27 nov")

    monkeypatch.setattr("app.services.jira_epic.list_qc_sprints", lambda: [sprint])
    monkeypatch.setattr("app.services.jira_epic._search", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("app.services.jira_epic._create_issue", lambda _fields: next(keys))
    monkeypatch.setattr("app.services.jira_epic._account_id", lambda: None)
    monkeypatch.setattr("app.services.jira_epic._put_fields", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.services.jira_epic._read_labels", lambda _key: ["qcpulse"])
    monkeypatch.setattr("app.services.jira_epic._attach_release_note", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "app.services.jira_epic._post_sprint_issues",
        lambda sprint_id, issue_keys: moved.append((sprint_id, list(issue_keys))),
    )

    result = publish_epic(draft, 27623)

    assert result.key == "QCO-1"
    assert result.task_key == "QCO-2"
    assert result.subtask_count == 3
    assert result.sprint_id == 27623
    assert result.sprint_label == "Sprint 49 · 16 nov – 27 nov"
    assert moved == [(27623, ["QCO-1", "QCO-2", "QCO-3", "QCO-4", "QCO-5"])]


def test_unknown_sprint_is_rejected_before_creating_issues(monkeypatch) -> None:
    draft = EpicDraft(
        release_id=4,
        summary="WEBCL | 16.11.3 | HOTFIX",
        description="Objetivo",
        activity_type="HotFix",
        environment="FEHF",
    )
    monkeypatch.setattr(
        "app.services.jira_epic.list_qc_sprints",
        lambda: [SprintChoice(id=27623, name="Sprint 49", state="future", label="Sprint 49")],
    )
    monkeypatch.setattr("app.services.jira_epic._create_issue", lambda _fields: (_ for _ in ()).throw(AssertionError("no crea")))

    with pytest.raises(JiraEpicError, match="tablero de QC"):
        publish_epic(draft, 999)


def test_sprint_move_keeps_each_issue_once_per_batch(monkeypatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr("app.services.jira_epic._post_sprint_issues", lambda _sprint_id, keys: calls.append(list(keys)))
    _move_issues_to_sprint(27624, ["QCO-1", "QCO-1", *[f"QCO-{index}" for index in range(2, 53)]])
    assert [len(call) for call in calls] == [50, 2]
    assert calls[0].count("QCO-1") == 1


def test_pdf_upload_is_multipart() -> None:
    client = httpx.Client(headers={"Accept": "application/json", "X-Atlassian-Token": "no-check"})
    request = client.build_request(
        "POST",
        "https://example.test/rest/api/3/issue/QCO-49805/attachments",
        files={"file": ("RN.pdf", b"%PDF", "application/pdf")},
    )
    assert request.headers["content-type"].startswith("multipart/form-data")


def test_jira_sprints_is_not_read_as_a_release_id(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.releases.list_qc_sprints",
        lambda: [SprintChoice(id=27623, name="Sprint 49", state="future", label="Sprint 49 · 16 nov – 27 nov")],
    )
    response = client.get("/api/v1/releases/jira-sprints")
    assert response.status_code == 200
    assert response.json() == [
        {"id": 27623, "name": "Sprint 49", "state": "future", "label": "Sprint 49 · 16 nov – 27 nov"}
    ]


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
