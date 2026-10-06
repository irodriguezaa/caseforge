"""Sprint Testing: B/A/C-style buckets for Technical Epics from Jira filters."""

from tests.conftest import login_as
from app.services.sprint_testing.catalog import get_swf
from app.services.sprint_testing.classify import classify_status, is_technical_epic
from app.services.sprint_testing.service import aggregate_issues, build_sprint_testing


def _issue(key: str, project: str, status: str, issuetype: str = "Technical Epic") -> dict:
    return {
        "key": key,
        "fields": {
            "issuetype": {"name": issuetype},
            "status": {"name": status},
            "project": {"key": project},
            "summary": key,
        },
    }


def test_classify_aliases() -> None:
    assert classify_status("Tareas por hacer") == ("todo", "To Do")
    assert classify_status("To Do") == ("todo", "To Do")
    assert classify_status("Validation") == ("testing", "QC Validation")
    assert classify_status("Validate QC") == ("testing", "QC Validation")
    assert classify_status("QC Validation") == ("testing", "QC Validation")
    assert classify_status("QA Validation") == ("testing", "QA Validation")
    assert classify_status("Cancelled") == ("closed", "Canceled")
    assert classify_status("Canceled") == ("closed", "Canceled")
    assert classify_status("Finalizada") == ("closed", "Finalizada")
    assert classify_status("In Progress") == ("development", "In Progress")
    assert classify_status("Blocked") == ("development", "Blocked")
    assert classify_status("Released", "done") == ("closed", "Released")
    assert classify_status("QA Validation", "done") == ("testing", "QA Validation")


def test_only_technical_epic_is_counted() -> None:
    assert is_technical_epic("Technical Epic")
    assert is_technical_epic(" technical epic ")
    assert not is_technical_epic("Epic")
    assert not is_technical_epic("Story")
    assert not is_technical_epic("QA Bug")


def test_adt_example_graph1_and_graph2() -> None:
    statuses = (
        ["To Do"] * 2
        + ["In Progress"] * 5
        + ["Blocked"]
        + ["Development"] * 4
        + ["Integration"] * 3
        + ["QA Validation"] * 2
        + ["QC Validation"]
        + ["Roll Out"] * 2
        + ["Done"] * 4
        + ["Canceled"]
    )
    issues = [_issue(f"ADTCL-{index}", "ADTCL", status) for index, status in enumerate(statuses, start=1)]
    issues.append(_issue("ADTCL-999", "ADTCL", "In Progress", issuetype="Story"))
    issues.append(_issue("WINCL-1", "WINCL", "Done"))
    hitss = get_swf("hitss")
    assert hitss is not None
    payload = aggregate_issues("44", "Sprint 44", "117698", hitss, issues)
    adt = next(row for row in payload.programs if row.program_key == "ADTCL")
    assert adt.todo == {"To Do": 2}
    assert adt.development == {"In Progress": 5, "Blocked": 1, "Development": 4}
    assert adt.testing == {"Integration": 3, "QA Validation": 2, "QC Validation": 1}
    assert adt.closed == {"Roll Out": 2, "Done": 4, "Canceled": 1}
    assert adt.total == 25
    assert adt.open == 18
    assert adt.closed_total == 7
    assert adt.consistency_ok is True
    assert sum(adt.development.values()) + sum(adt.testing.values()) + sum(adt.closed.values()) + sum(
        adt.todo.values()
    ) == adt.total
    assert adt.open + adt.closed_total == adt.total
    win = next(row for row in payload.programs if row.program_key == "WINCL")
    assert win.total == 1
    assert all(row.program_key not in {"AAFCL", "STVCL", "WEBCL"} for row in payload.programs)
    assert payload.other_issue_count == 1
    assert payload.technical_epic_count == 26
    assert payload.consistency_ok is True


def test_done_category_moves_open_to_closed() -> None:
    hitss = get_swf("hitss")
    assert hitss is not None
    issues = [_issue(f"ADTCL-{i}", "ADTCL", "In Progress") for i in range(1, 8)]
    extra = []
    for index in range(8, 15):
        extra.append(
            {
                "key": f"ADTCL-{index}",
                "fields": {
                    "issuetype": {"name": "Technical Epic"},
                    "status": {"name": "Finalizada", "statusCategory": {"key": "done"}},
                    "project": {"key": "ADTCL"},
                    "summary": f"ADTCL-{index}",
                },
            }
        )
    payload = aggregate_issues("44", "Sprint 44", "117698", hitss, issues + extra)
    adt = payload.programs[0]
    assert adt.open == 7
    assert adt.closed_total == 7
    assert adt.closed.get("Finalizada") == 7


def test_zero_programs_are_omitted() -> None:
    hitss = get_swf("hitss")
    assert hitss is not None
    payload = aggregate_issues(
        "44",
        "Sprint 44",
        "117698",
        hitss,
        [_issue("WEBCL-1", "WEBCL", "Integration")],
    )
    assert [row.program_key for row in payload.programs] == ["WEBCL"]


def test_sprint_46_is_not_actionable(client) -> None:
    response = client.get("/api/v1/sprint-testing", params={"sprint": "46", "swf": "hitss"})
    assert response.status_code == 400
    assert "Saved Filter" in response.json()["detail"]


def test_options_mark_future_sprints(client) -> None:
    response = client.get("/api/v1/sprint-testing/options")
    assert response.status_code == 200
    body = response.json()
    by_id = {item["id"]: item for item in body["sprints"]}
    assert by_id["44"]["actionable"] is True
    assert by_id["44"]["filter_id"] == "117698"
    assert by_id["45"]["actionable"] is True
    assert by_id["45"]["filter_id"] == "117703"
    assert by_id["46"]["actionable"] is False


def test_tester_and_consulta_cannot_read(client) -> None:
    login_as(client, "tester@test.com", "tester-pass")
    denied = client.get("/api/v1/sprint-testing/options")
    assert denied.status_code == 403
    login_as(client, "consulta@test.com", "consulta-pass")
    denied_consulta = client.get("/api/v1/sprint-testing", params={"sprint": "44", "swf": "hitss"})
    assert denied_consulta.status_code == 403


def test_build_paginates_and_dedupes(monkeypatch) -> None:
    from app.services import jira_client

    pages = [
        {
            "issues": [
                _issue("ADTCL-1", "ADTCL", "In Progress"),
                _issue("ADTCL-1", "ADTCL", "In Progress"),
            ],
            "nextPageToken": "page-2",
        },
        {
            "issues": [_issue("ADTCL-2", "ADTCL", "To Do")],
            "nextPageToken": None,
        },
    ]

    class _FakeResponse:
        status_code = 200

        def __init__(self, payload: dict) -> None:
            self._payload = payload

        def json(self) -> dict:
            return self._payload

    class _FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def get(self, path: str) -> _FakeResponse:
            assert path == "/rest/api/3/filter/117698"
            return _FakeResponse({"jql": "project in (ADTCL, WINCL)"})

        def post(self, path: str, json: dict) -> _FakeResponse:
            assert path == "/rest/api/3/search/jql"
            if json.get("nextPageToken") == "page-2":
                return _FakeResponse(pages[1])
            return _FakeResponse(pages[0])

    monkeypatch.setattr(jira_client, "ensure_authenticated", lambda: None)
    monkeypatch.setattr(jira_client, "_client", lambda: _FakeClient())
    payload = build_sprint_testing("44", "hitss")
    assert payload.programs[0].total == 2
    assert payload.programs[0].open == 2
    assert payload.filter_issue_count == 2
