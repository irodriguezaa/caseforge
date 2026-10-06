"""Sprint Testing: B/A/C-style buckets for Technical Epics from Jira filters."""

from tests.conftest import login_as
from app.services.sprint_testing.catalog import get_swf
from app.services.sprint_testing.classify import classify_status, is_blocker_priority, is_technical_epic
from app.services.sprint_testing.service import aggregate_execution_issues, aggregate_issues, build_sprint_testing


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
    assert classify_status("Data Validation") == ("closed", "Data Validation")
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


def test_blocker_priority_aliases() -> None:
    assert is_blocker_priority("Blocker") is True
    assert is_blocker_priority("Supone un impedimento") is True
    assert is_blocker_priority("Impedimento") is True
    assert is_blocker_priority("Critical") is False
    assert is_blocker_priority("Major") is False


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


def test_execution_counts_blocker_by_program() -> None:
    hitss = get_swf("hitss")
    assert hitss is not None

    def _exec(key: str, project: str, priority: str) -> dict:
        return {
            "key": key,
            "fields": {
                "issuetype": {"name": "Bug"},
                "status": {"name": "In Progress"},
                "project": {"key": project},
                "priority": {"name": priority},
                "summary": key,
            },
        }

    payload = aggregate_execution_issues(
        "117704",
        hitss,
        [
            _exec("ADTCL-1", "ADTCL", "Blocker"),
            _exec("ADTCL-2", "ADTCL", "Major"),
            _exec("ADTCL-3", "ADTCL", "Impedimento"),
            _exec("WINCL-1", "WINCL", "Critical"),
        ],
    )
    assert payload.filter_id == "117704"
    assert payload.issue_count == 4
    adt = next(row for row in payload.programs if row.program_key == "ADTCL")
    assert adt.blocker == 2
    assert adt.non_blocker == 1
    assert adt.total == 3
    win = next(row for row in payload.programs if row.program_key == "WINCL")
    assert win.blocker == 0
    assert win.non_blocker == 1
    assert [row.key for row in payload.blockers] == ["ADTCL-1", "ADTCL-3"]
    assert payload.blockers[0].summary == "ADTCL-1"
    assert payload.blockers[0].status == "In Progress"
    assert all(row.program_key not in {"WEBCL", "AAFCL"} for row in payload.programs)


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
    assert by_id["44"]["execution_filter_id"] == "117704"
    assert by_id["45"]["actionable"] is True
    assert by_id["45"]["filter_id"] == "117703"
    assert by_id["45"]["execution_filter_id"] is None
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
            if path.endswith("117704"):
                return _FakeResponse({"jql": "execution"})
            assert path == "/rest/api/3/filter/117698"
            return _FakeResponse({"jql": "project in (ADTCL, WINCL)"})

        def post(self, path: str, json: dict) -> _FakeResponse:
            assert path == "/rest/api/3/search/jql"
            if json.get("jql") == "execution":
                return _FakeResponse({"issues": [], "nextPageToken": None})
            if json.get("nextPageToken") == "page-2":
                return _FakeResponse(pages[1])
            return _FakeResponse(pages[0])

    monkeypatch.setattr(jira_client, "ensure_authenticated", lambda: None)
    monkeypatch.setattr(jira_client, "_client", lambda: _FakeClient())
    payload = build_sprint_testing("44", "hitss")
    assert payload.programs[0].total == 2
    assert payload.programs[0].open == 2
    assert payload.filter_issue_count == 2


def _exec_issue(
    key: str,
    project: str,
    status: str,
    priority: str,
    summary: str,
    description: object,
    issuetype: str = "QA Bug",
) -> dict:
    return {
        "key": key,
        "fields": {
            "issuetype": {"name": issuetype},
            "status": {"name": status},
            "project": {"key": project},
            "priority": {"name": priority},
            "summary": summary,
            "description": description,
        },
    }


def test_execution_issue_rows_filter_and_truncate() -> None:
    from app.services.sprint_testing.service import list_execution_issue_rows

    hitss = get_swf("hitss")
    assert hitss is not None
    rows = list_execution_issue_rows(
        hitss,
        [
            _exec_issue(
                "ADTCL-1",
                "ADTCL",
                "In Progress",
                "Blocker",
                "Playback VOD",
                {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "falla"}]}]},
            ),
            _exec_issue("ATSCL-9", "ATSCL", "To Do", "Major", "Otro SWF", "fuera"),
            _exec_issue("WINCL-2", "WINCL", "QA Validation", "Minor", "Layout", "x" * 600, issuetype="QC Bug"),
        ],
    )
    assert [row.key for row in rows] == ["ADTCL-1", "WINCL-2"]
    assert rows[0].device == "ADT / FireTV"
    assert rows[0].summary == "Playback VOD"
    assert rows[0].status == "In Progress"
    assert rows[0].priority == "Blocker"
    assert rows[1].summary == "Layout"


def test_issues_workbook_headers() -> None:
    from io import BytesIO

    from openpyxl import load_workbook

    from app.schemas.sprint_testing import ExecutionIssueRow
    from app.services.sprint_testing.export import ISSUE_HEADERS, build_issues_workbook

    payload = build_issues_workbook(
        [
            ExecutionIssueRow(
                key="ADTCL-1",
                summary="Playback",
                status="In Progress",
                priority="Blocker",
                device="ADT / FireTV",
                program_key="ADTCL",
            )
        ]
    )
    book = load_workbook(BytesIO(payload))
    sheet = book.active
    assert [cell.value for cell in sheet[1]] == ISSUE_HEADERS
    assert sheet["A2"].value == "ADTCL-1"
    assert sheet["C2"].value == "In Progress"
    assert sheet["D2"].value == "Blocker"


def test_executive_pptx_is_one_slide_without_open_column() -> None:
    from io import BytesIO

    from pptx import Presentation

    from app.schemas.sprint_testing import (
        ExecutionBlockerRow,
        ExecutionMetrics,
        ExecutionProgramMetrics,
        ProgramMetrics,
        SprintTestingRead,
        SprintTestingSprint,
    )
    from app.services.sprint_testing.export import build_executive_pptx

    payload = SprintTestingRead(
        sprint=SprintTestingSprint(id="44", label="Sprint 44", filter_id="117698"),
        swf="Hitss",
        filter_issue_count=10,
        technical_epic_count=5,
        other_issue_count=0,
        programs=[
            ProgramMetrics(
                program_key="ADTCL",
                display_name="ADT / FireTV",
                total=5,
                todo={"To Do": 1},
                development={"In Progress": 2},
                testing={"QA Validation": 1},
                closed={"Done": 1},
                open=4,
                closed_total=1,
                unclassified={},
                consistency_ok=True,
            )
        ],
        consistency_ok=True,
        execution=ExecutionMetrics(
            filter_id="117704",
            issue_count=3,
            programs=[
                ExecutionProgramMetrics(
                    program_key="ADTCL",
                    display_name="ADT / FireTV",
                    total=3,
                    blocker=1,
                    non_blocker=2,
                )
            ],
            blockers=[
                ExecutionBlockerRow(key="ADTCL-1", summary="Playback VOD", status="In Progress"),
            ],
        ),
    )
    deck = Presentation(BytesIO(build_executive_pptx(payload)))
    assert len(deck.slides) == 1
    tables = [shape.table for shape in deck.slides[0].shapes if shape.has_table]
    assert len(tables) == 2
    epic_headers = [tables[0].cell(0, col).text.strip() for col in range(len(tables[0].columns))]
    issue_headers = [tables[1].cell(0, col).text.strip() for col in range(len(tables[1].columns))]
    assert "To Do" not in epic_headers
    assert "Abierto" not in epic_headers
    assert epic_headers == ["Dispositivo", "Desarrollo", "Testing", "Cerrado", "Total"]
    assert issue_headers == ["Dispositivo", "Blocker", "No Blocker", "Total"]
    texts = [shape.text_frame.text for shape in deck.slides[0].shapes if shape.has_text_frame]
    assert not any(text.strip() == "Blockers" for text in texts)


def test_export_issues_requires_execution_filter(client) -> None:
    response = client.get("/api/v1/sprint-testing/export/issues", params={"sprint": "45", "swf": "hitss"})
    assert response.status_code == 400
    assert "ejecución" in response.json()["detail"]


def test_tester_cannot_export(client) -> None:
    login_as(client, "tester@test.com", "tester-pass")
    denied = client.get("/api/v1/sprint-testing/export/report", params={"sprint": "44", "swf": "hitss"})
    assert denied.status_code == 403
