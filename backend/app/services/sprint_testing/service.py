"""Aggregate Technical Epics from a Sprint saved filter by SWF program."""

from __future__ import annotations

from typing import Any

from app.schemas.sprint_testing import (
    ExecutionIssueRow,
    ExecutionMetrics,
    ExecutionProgramMetrics,
    ProgramMetrics,
    ProgramOption,
    SprintOption,
    SprintTestingOptions,
    SprintTestingRead,
    SprintTestingSprint,
    SwfOption,
)
from app.services.jira_client import fetch_raw_issues_by_filter
from app.services.jira_generation import adf_to_text
from app.services.sprint_testing.catalog import SWFS, SPRINTS, SprintDef, SwfDef, get_sprint, get_swf
from app.services.sprint_testing.classify import classify_status, is_blocker_priority, is_technical_epic
from app.services.sprint_testing.export import build_executive_pptx, build_issues_workbook

_ISSUE_FIELDS = ["summary", "issuetype", "status", "project"]
_EXECUTION_FIELDS = ["summary", "issuetype", "status", "project", "priority"]
_EXPORT_FIELDS = ["summary", "description", "issuetype", "status", "project", "priority"]
_DESCRIPTION_MAX = 500


class SprintTestingConfigError(ValueError):
    """Unknown sprint/SWF or sprint without a saved filter yet."""


def list_options() -> SprintTestingOptions:
    return SprintTestingOptions(
        sprints=[
            SprintOption(
                id=item.id,
                label=item.label,
                filter_id=item.filter_id,
                execution_filter_id=item.execution_filter_id,
                actionable=bool(item.filter_id),
            )
            for item in SPRINTS
        ],
        swfs=[
            SwfOption(
                id=item.id,
                label=item.label,
                programs=[
                    ProgramOption(program_key=program.program_key, display_name=program.display_name)
                    for program in item.programs
                ],
            )
            for item in SWFS
        ],
    )


def _sum_counts(values: dict[str, int]) -> int:
    return sum(values.values())


def _program_metrics(program_key: str, display_name: str, issues: list[dict[str, Any]]) -> ProgramMetrics:
    todo: dict[str, int] = {}
    development: dict[str, int] = {}
    testing: dict[str, int] = {}
    closed: dict[str, int] = {}
    for issue in issues:
        fields = issue.get("fields") or {}
        status_obj = fields.get("status") or {}
        status = (status_obj.get("name") or "").strip()
        category = ((status_obj.get("statusCategory") or {}).get("key") or "").strip()
        bucket, label = classify_status(status, category)
        target = {"todo": todo, "development": development, "testing": testing, "closed": closed}[bucket]
        target[label] = target.get(label, 0) + 1
    total = len(issues)
    closed_total = _sum_counts(closed)
    open_count = total - closed_total
    chart1 = _sum_counts(development) + _sum_counts(testing) + closed_total + _sum_counts(todo)
    consistency_ok = chart1 == total and open_count + closed_total == total
    return ProgramMetrics(
        program_key=program_key,
        display_name=display_name,
        total=total,
        todo=todo,
        development=development,
        testing=testing,
        closed=closed,
        open=open_count,
        closed_total=closed_total,
        unclassified={},
        consistency_ok=consistency_ok,
    )


def _project_key(issue: dict[str, Any]) -> str:
    fields = issue.get("fields") or {}
    project = fields.get("project") or {}
    return str(project.get("key") or "").strip().upper()


def _issuetype_name(issue: dict[str, Any]) -> str:
    fields = issue.get("fields") or {}
    return str((fields.get("issuetype") or {}).get("name") or "")


def _priority_name(issue: dict[str, Any]) -> str:
    fields = issue.get("fields") or {}
    return str((fields.get("priority") or {}).get("name") or "")


def _status_name(issue: dict[str, Any]) -> str:
    fields = issue.get("fields") or {}
    return str((fields.get("status") or {}).get("name") or "")


def _summary(issue: dict[str, Any]) -> str:
    fields = issue.get("fields") or {}
    return str(fields.get("summary") or "").strip()


def _description(issue: dict[str, Any]) -> str:
    fields = issue.get("fields") or {}
    text = adf_to_text(fields.get("description")).strip()
    if len(text) > _DESCRIPTION_MAX:
        return text[: _DESCRIPTION_MAX - 1].rstrip() + "…"
    return text


def _resolve_sprint_swf(sprint_id: str, swf_id: str) -> tuple[SprintDef, SwfDef]:
    sprint = get_sprint(sprint_id)
    if sprint is None:
        raise SprintTestingConfigError("Sprint no reconocido.")
    swf = get_swf(swf_id)
    if swf is None:
        raise SprintTestingConfigError("SWF no reconocido.")
    return sprint, swf


def export_basename(sprint_label: str, swf_label: str) -> str:
    return f"{sprint_label.replace(' ', '')}_{swf_label.replace(' ', '')}"


def list_execution_issue_rows(swf: SwfDef, issues: list[dict[str, Any]]) -> list[ExecutionIssueRow]:
    wanted = {program.program_key.upper(): program for program in swf.programs}
    rows: list[ExecutionIssueRow] = []
    for issue in issues:
        program = wanted.get(_project_key(issue))
        if program is None:
            continue
        rows.append(
            ExecutionIssueRow(
                key=str(issue.get("key") or "").strip().upper(),
                issue_type=_issuetype_name(issue).strip(),
                summary=_summary(issue),
                description=_description(issue),
                status=_status_name(issue),
                priority=_priority_name(issue),
                device=program.display_name,
                program_key=program.program_key,
            )
        )
    rows.sort(key=lambda row: (row.device, row.key))
    return rows


def build_execution_issues_xlsx(sprint_id: str, swf_id: str) -> tuple[bytes, str]:
    sprint, swf = _resolve_sprint_swf(sprint_id, swf_id)
    if not sprint.execution_filter_id:
        raise SprintTestingConfigError(
            f"{sprint.label} aún no tiene un Saved Filter de issues en ejecución."
        )
    issues = fetch_raw_issues_by_filter(sprint.execution_filter_id, _EXPORT_FIELDS)
    rows = list_execution_issue_rows(swf, issues)
    filename = f"{export_basename(sprint.label, swf.label)}_issues.xlsx"
    return build_issues_workbook(rows), filename


def build_executive_report_pptx(sprint_id: str, swf_id: str) -> tuple[bytes, str]:
    payload = build_sprint_testing(sprint_id, swf_id)
    filename = f"{export_basename(payload.sprint.label, payload.swf)}_ejecutivo.pptx"
    return build_executive_pptx(payload), filename


def aggregate_execution_issues(
    filter_id: str,
    swf: SwfDef,
    issues: list[dict[str, Any]],
) -> ExecutionMetrics:
    grouped: dict[str, list[dict[str, Any]]] = {program.program_key.upper(): [] for program in swf.programs}
    for issue in issues:
        key = _project_key(issue)
        if key in grouped:
            grouped[key].append(issue)
    programs: list[ExecutionProgramMetrics] = []
    for program in swf.programs:
        rows = grouped[program.program_key]
        if not rows:
            continue
        blocker = sum(1 for issue in rows if is_blocker_priority(_priority_name(issue)))
        programs.append(
            ExecutionProgramMetrics(
                program_key=program.program_key,
                display_name=program.display_name,
                total=len(rows),
                blocker=blocker,
                non_blocker=len(rows) - blocker,
            )
        )
    return ExecutionMetrics(
        filter_id=filter_id,
        issue_count=sum(row.total for row in programs),
        programs=programs,
    )


def build_sprint_testing(sprint_id: str, swf_id: str) -> SprintTestingRead:
    sprint, swf = _resolve_sprint_swf(sprint_id, swf_id)
    if not sprint.filter_id:
        raise SprintTestingConfigError(
            f"{sprint.label} aún no tiene un Saved Filter configurado."
        )
    issues = fetch_raw_issues_by_filter(sprint.filter_id, _ISSUE_FIELDS)
    payload = aggregate_issues(sprint.id, sprint.label, sprint.filter_id, swf, issues)
    if sprint.execution_filter_id:
        execution_issues = fetch_raw_issues_by_filter(sprint.execution_filter_id, _EXECUTION_FIELDS)
        payload.execution = aggregate_execution_issues(sprint.execution_filter_id, swf, execution_issues)
    return payload


def aggregate_issues(
    sprint_id: str,
    sprint_label: str,
    filter_id: str,
    swf: SwfDef,
    issues: list[dict[str, Any]],
) -> SprintTestingRead:
    wanted = {program.program_key.upper(): program for program in swf.programs}
    grouped: dict[str, list[dict[str, Any]]] = {key: [] for key in wanted}
    other_issue_count = 0
    for issue in issues:
        if not is_technical_epic(_issuetype_name(issue)):
            other_issue_count += 1
            continue
        key = _project_key(issue)
        if key in grouped:
            grouped[key].append(issue)
    programs = [
        _program_metrics(program.program_key, program.display_name, grouped[program.program_key])
        for program in swf.programs
        if grouped[program.program_key]
    ]
    technical_epic_count = sum(row.total for row in programs)
    consistency_ok = all(row.consistency_ok for row in programs)
    return SprintTestingRead(
        sprint=SprintTestingSprint(id=sprint_id, label=sprint_label, filter_id=filter_id),
        swf=swf.label,
        filter_issue_count=len(issues),
        technical_epic_count=technical_epic_count,
        other_issue_count=other_issue_count,
        programs=programs,
        consistency_ok=consistency_ok,
    )
