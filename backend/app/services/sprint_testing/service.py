"""Aggregate Technical Epics from a Sprint saved filter by SWF program."""

from __future__ import annotations

from typing import Any

from app.schemas.sprint_testing import (
    ProgramMetrics,
    ProgramOption,
    SprintOption,
    SprintTestingOptions,
    SprintTestingRead,
    SprintTestingSprint,
    SwfOption,
)
from app.services.jira_client import fetch_raw_issues_by_filter
from app.services.sprint_testing.catalog import SWFS, SPRINTS, SwfDef, get_sprint, get_swf
from app.services.sprint_testing.classify import classify_status, is_technical_epic

_ISSUE_FIELDS = ["summary", "issuetype", "status", "project"]


class SprintTestingConfigError(ValueError):
    """Unknown sprint/SWF or sprint without a saved filter yet."""


def list_options() -> SprintTestingOptions:
    return SprintTestingOptions(
        sprints=[
            SprintOption(
                id=item.id,
                label=item.label,
                filter_id=item.filter_id,
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
        status = ((fields.get("status") or {}).get("name") or "").strip()
        bucket, label = classify_status(status)
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


def build_sprint_testing(sprint_id: str, swf_id: str) -> SprintTestingRead:
    sprint = get_sprint(sprint_id)
    if sprint is None:
        raise SprintTestingConfigError("Sprint no reconocido.")
    if not sprint.filter_id:
        raise SprintTestingConfigError(
            f"{sprint.label} aún no tiene un Saved Filter configurado."
        )
    swf = get_swf(swf_id)
    if swf is None:
        raise SprintTestingConfigError("SWF no reconocido.")
    issues = fetch_raw_issues_by_filter(sprint.filter_id, _ISSUE_FIELDS)
    return aggregate_issues(sprint.id, sprint.label, sprint.filter_id, swf, issues)


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
