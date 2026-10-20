"""Aggregate Technical Epics from a Sprint saved filter by SWF program."""

from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime
from typing import Any

from app.schemas.sprint_testing import (
    ExecutionBlockerRow,
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
from app.services.sprint_testing.catalog import SWFS, SPRINTS, ProgramDef, SprintDef, SwfDef, get_sprint, get_swf
from app.services.sprint_testing.device_filters import sprint_device_filters
from app.services.sprint_testing.classify import (
    classify_status,
    is_blocker_priority,
    is_closed_status,
    is_technical_epic,
)
from app.services.sprint_testing.export import (
    build_executive_pptx,
    build_executive_pptx_pack,
    build_issues_workbook,
    build_issues_workbook_sheets,
)
from app.services.sprint_testing.pack import pack_email_allowed, pack_swfs

_ISSUE_FIELDS = ["summary", "issuetype", "status", "project"]
_EXECUTION_FIELDS = [
    "summary",
    "status",
    "project",
    "priority",
    "issuetype",
    "created",
    "parent",
    "comment",
    "issuelinks",
]
_EXECUTION_EXPAND = ["changelog"]
_NESTED_LINK_TYPE = "nested for resolution"
_JIRA_OFFSET_RE = re.compile(r"([+-])(\d{2})(\d{2})$")


class SprintTestingConfigError(ValueError):
    """Unknown sprint/SWF or sprint without a saved filter yet."""


def _swf_option(item: SwfDef) -> SwfOption:
    return SwfOption(
        id=item.id,
        label=item.label,
        programs=[
            ProgramOption(program_key=program.program_key, display_name=program.display_name)
            for program in item.programs
        ],
    )


def list_options(email: str | None = None) -> SprintTestingOptions:
    selected = pack_swfs() if pack_email_allowed(email) else []
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
        swfs=[_swf_option(item) for item in SWFS],
        pack_available=bool(selected),
        pack_swfs=[_swf_option(item) for item in selected],
    )


def _sum_counts(values: dict[str, int]) -> int:
    return sum(values.values())


def _program_metrics(program_key: str, display_name: str, issues: list[dict[str, Any]]) -> ProgramMetrics:
    todo: dict[str, int] = {}
    development: dict[str, int] = {}
    integration: dict[str, int] = {}
    testing: dict[str, int] = {}
    closed: dict[str, int] = {}
    for issue in issues:
        fields = issue.get("fields") or {}
        status_obj = fields.get("status") or {}
        status = (status_obj.get("name") or "").strip()
        category = ((status_obj.get("statusCategory") or {}).get("key") or "").strip()
        bucket, label = classify_status(status, category)
        target = {
            "todo": todo,
            "development": development,
            "integration": integration,
            "testing": testing,
            "closed": closed,
        }[bucket]
        target[label] = target.get(label, 0) + 1
    total = len(issues)
    closed_total = _sum_counts(closed)
    open_count = total - closed_total
    chart1 = (
        _sum_counts(development)
        + _sum_counts(integration)
        + _sum_counts(testing)
        + closed_total
        + _sum_counts(todo)
    )
    consistency_ok = chart1 == total and open_count + closed_total == total
    return ProgramMetrics(
        program_key=program_key,
        display_name=display_name,
        total=total,
        todo=todo,
        development=development,
        integration=integration,
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


def _status_category_key(issue: dict[str, Any]) -> str | None:
    fields = issue.get("fields") or {}
    category = (fields.get("status") or {}).get("statusCategory") or {}
    key = category.get("key")
    return str(key) if key else None


def _summary(issue: dict[str, Any]) -> str:
    fields = issue.get("fields") or {}
    return str(fields.get("summary") or "").strip()


def _parse_jira_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    text = raw.strip().replace("Z", "+00:00")
    match = _JIRA_OFFSET_RE.search(text)
    if match:
        text = text[: match.start()] + f"{match.group(1)}{match.group(2)}:{match.group(3)}"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        try:
            return datetime.strptime(text[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return None


def _created_at(issue: dict[str, Any]) -> str | None:
    raw = (issue.get("fields") or {}).get("created")
    return str(raw).strip() if raw else None


def _principal_key(issue: dict[str, Any]) -> str | None:
    parent = (issue.get("fields") or {}).get("parent") or {}
    key = str(parent.get("key") or "").strip().upper()
    return key or None


def _last_status_change(issue: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    histories = (issue.get("changelog") or {}).get("histories") or []
    best_dt: datetime | None = None
    best: tuple[str | None, str | None, str | None] = (None, None, None)
    for history in histories:
        when = history.get("created")
        parsed = _parse_jira_datetime(when)
        if parsed is None:
            continue
        for item in history.get("items") or []:
            if str(item.get("field") or "").strip().lower() != "status":
                continue
            if best_dt is None or parsed > best_dt:
                best_dt = parsed
                best = (
                    str(when) if when else None,
                    str(item.get("fromString") or "").strip() or None,
                    str(item.get("toString") or "").strip() or None,
                )
    return best


def _comment_author(raw: Any) -> str | None:
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("displayName") or raw.get("name") or "").strip()
    return name or None


def _last_comment(issue: dict[str, Any]) -> tuple[str | None, str | None]:
    best_dt: datetime | None = None
    best: tuple[str | None, str | None] = (None, None)

    def consider(when: str | None, author: str | None) -> None:
        nonlocal best_dt, best
        parsed = _parse_jira_datetime(when)
        if parsed is None:
            return
        if best_dt is None or parsed > best_dt:
            best_dt = parsed
            best = (when, author)

    comments = ((issue.get("fields") or {}).get("comment") or {}).get("comments") or []
    for comment in comments:
        consider(
            comment.get("updated") or comment.get("created"),
            _comment_author(comment.get("author")),
        )
    for history in (issue.get("changelog") or {}).get("histories") or []:
        items = history.get("items") or []
        if any(str(item.get("field") or "").strip().lower() == "comment" for item in items):
            consider(history.get("created"), _comment_author(history.get("author")))
    return best


def _format_jira_clock(raw: str | None) -> str:
    parsed = _parse_jira_datetime(raw)
    if parsed is None:
        return ""
    return parsed.strftime("%d/%m/%Y %H:%M")


def _status_change_label(issue: dict[str, Any]) -> str:
    when, source, target = _last_status_change(issue)
    stamp = _format_jira_clock(when)
    if not stamp:
        return ""
    if source and target:
        return f"{stamp} · {source} → {target}"
    return stamp


def _last_comment_label(issue: dict[str, Any]) -> str:
    when, author = _last_comment(issue)
    stamp = _format_jira_clock(when)
    if not stamp:
        return ""
    if author:
        return f"{stamp} · {author}"
    return stamp


def _nested_issue_keys(issue: dict[str, Any]) -> list[str]:
    own = str(issue.get("key") or "").strip().upper()
    keys: list[str] = []
    seen: set[str] = set()
    for link in (issue.get("fields") or {}).get("issuelinks") or []:
        link_type = str((link.get("type") or {}).get("name") or "").strip().lower()
        if link_type != _NESTED_LINK_TYPE:
            continue
        for side in ("outwardIssue", "inwardIssue"):
            other = link.get(side) or {}
            key = str(other.get("key") or "").strip().upper()
            if not key or key == own or key in seen:
                continue
            seen.add(key)
            keys.append(key)
    return keys


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


def _issue_key(issue: dict[str, Any]) -> str:
    return str(issue.get("key") or "").strip().upper()


def _cached_execution_issues(cache: dict[str, list[dict[str, Any]]], filter_id: str) -> list[dict[str, Any]]:
    if filter_id not in cache:
        cache[filter_id] = fetch_raw_issues_by_filter(
            filter_id,
            _EXECUTION_FIELDS,
            expand=_EXECUTION_EXPAND,
        )
    return cache[filter_id]


def collect_execution_issues(
    sprint: SprintDef,
    swf: SwfDef,
    cache: dict[str, list[dict[str, Any]]] | None = None,
) -> tuple[str, dict[str, list[dict[str, Any]]]]:
    """Device QA+QC filters from env, else the sprint execution filter grouped by project."""
    store = cache if cache is not None else {}
    mapping = sprint_device_filters(sprint.id)
    grouped: dict[str, list[dict[str, Any]]] = {program.program_key.upper(): [] for program in swf.programs}
    if mapping:
        used: list[str] = []
        for program in swf.programs:
            pair = mapping.get(program.program_key.upper())
            if pair is None:
                continue
            by_key: dict[str, dict[str, Any]] = {}
            for filter_id in pair.filter_ids():
                used.append(filter_id)
                for issue in _cached_execution_issues(store, filter_id):
                    key = _issue_key(issue)
                    if key:
                        by_key.setdefault(key, issue)
            grouped[program.program_key] = list(by_key.values())
        return ",".join(dict.fromkeys(used)), grouped
    if not sprint.execution_filter_id:
        return "", grouped
    for issue in _cached_execution_issues(store, sprint.execution_filter_id):
        key = _project_key(issue)
        if key in grouped:
            grouped[key].append(issue)
    return sprint.execution_filter_id, grouped


def _program_for_issue(
    issue: dict[str, Any],
    wanted: dict[str, ProgramDef],
    assignment: dict[str, str] | None = None,
) -> ProgramDef | None:
    if assignment is not None:
        return wanted.get((assignment.get(_issue_key(issue)) or "").upper())
    return wanted.get(_project_key(issue))


def assignment_from_grouped(grouped: dict[str, list[dict[str, Any]]]) -> dict[str, str]:
    assignment: dict[str, str] = {}
    for program_key, rows in grouped.items():
        for issue in rows:
            key = _issue_key(issue)
            if key and key not in assignment:
                assignment[key] = program_key
    return assignment


def flatten_grouped(grouped: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rows in grouped.values():
        for issue in rows:
            key = _issue_key(issue)
            if not key or key in seen:
                continue
            seen.add(key)
            issues.append(issue)
    return issues


def list_blocker_issue_rows(
    swf: SwfDef,
    issues: list[dict[str, Any]],
    assignment: dict[str, str] | None = None,
) -> list[ExecutionIssueRow]:
    wanted = {program.program_key.upper(): program for program in swf.programs}
    rows: list[ExecutionIssueRow] = []
    for issue in issues:
        program = _program_for_issue(issue, wanted, assignment)
        if program is None:
            continue
        if not is_blocker_priority(_priority_name(issue)):
            continue
        if is_closed_status(_status_name(issue), _status_category_key(issue)):
            continue
        rows.append(
            ExecutionIssueRow(
                key=str(issue.get("key") or "").strip().upper(),
                summary=_summary(issue),
                status=_status_name(issue),
                priority=_priority_name(issue),
                device=program.display_name,
                program_key=program.program_key,
                issue_type=_issuetype_name(issue),
                created=_format_jira_clock(_created_at(issue)),
                principal=_principal_key(issue) or "",
                status_change=_status_change_label(issue),
                last_comment=_last_comment_label(issue),
                nested_issues=", ".join(_nested_issue_keys(issue)),
            )
        )
    rows.sort(key=lambda row: (row.device, row.key))
    return rows


def list_execution_issue_rows(
    swf: SwfDef,
    issues: list[dict[str, Any]],
    assignment: dict[str, str] | None = None,
) -> list[ExecutionIssueRow]:
    wanted = {program.program_key.upper(): program for program in swf.programs}
    rows: list[ExecutionIssueRow] = []
    for issue in issues:
        program = _program_for_issue(issue, wanted, assignment)
        if program is None:
            continue
        rows.append(
            ExecutionIssueRow(
                key=str(issue.get("key") or "").strip().upper(),
                summary=_summary(issue),
                status=_status_name(issue),
                priority=_priority_name(issue),
                device=program.display_name,
                program_key=program.program_key,
                issue_type=_issuetype_name(issue),
                created=_format_jira_clock(_created_at(issue)),
                principal=_principal_key(issue) or "",
                status_change=_status_change_label(issue),
                last_comment=_last_comment_label(issue),
                nested_issues=", ".join(_nested_issue_keys(issue)),
            )
        )
    rows.sort(key=lambda row: (row.device, row.key))
    return rows


def build_execution_issues_xlsx(sprint_id: str, swf_id: str) -> tuple[bytes, str]:
    sprint, swf = _resolve_sprint_swf(sprint_id, swf_id)
    if not sprint_device_filters(sprint.id) and not sprint.execution_filter_id:
        raise SprintTestingConfigError(
            f"{sprint.label} aún no tiene un Saved Filter de issues en ejecución."
        )
    _label, grouped = collect_execution_issues(sprint, swf)
    issues = flatten_grouped(grouped)
    rows = list_execution_issue_rows(swf, issues, assignment_from_grouped(grouped))
    filename = f"{export_basename(sprint.label, swf.label)}_issues.xlsx"
    return build_issues_workbook(rows), filename


def build_executive_report_pptx(sprint_id: str, swf_id: str) -> tuple[bytes, str]:
    payload = build_sprint_testing(sprint_id, swf_id)
    filename = f"{export_basename(payload.sprint.label, payload.swf)}_ejecutivo.pptx"
    return build_executive_pptx(payload), filename


def build_sprint_pack_zip(sprint_id: str) -> tuple[bytes, str]:
    sprint = get_sprint(sprint_id)
    if sprint is None:
        raise SprintTestingConfigError("Sprint no reconocido.")
    if not sprint.filter_id:
        raise SprintTestingConfigError(f"{sprint.label} aún no tiene un Saved Filter configurado.")
    selected = pack_swfs()
    if not selected:
        raise SprintTestingConfigError("No hay SWF configuradas para el pack (SPRINT_PACK_SWFS).")
    epic_issues = fetch_raw_issues_by_filter(sprint.filter_id, _ISSUE_FIELDS)
    cache: dict[str, list[dict[str, Any]]] = {}
    has_execution = bool(sprint_device_filters(sprint.id) or sprint.execution_filter_id)
    payloads: list[SprintTestingRead] = []
    sheets: list[tuple[str, list[ExecutionIssueRow]]] = []
    for swf in selected:
        payload = aggregate_issues(sprint.id, sprint.label, sprint.filter_id, swf, epic_issues)
        if has_execution:
            label, grouped = collect_execution_issues(sprint, swf, cache)
            payload.execution = aggregate_execution_issues(label, swf, grouped=grouped)
            sheets.append(
                (
                    swf.label,
                    list_blocker_issue_rows(swf, flatten_grouped(grouped), assignment_from_grouped(grouped)),
                )
            )
        else:
            sheets.append((swf.label, []))
        payloads.append(payload)
    pptx = build_executive_pptx_pack(payloads)
    xlsx = build_issues_workbook_sheets(sheets)
    labels = "_".join(item.label.replace(" ", "") for item in selected)
    base = export_basename(sprint.label, labels)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{base}_ejecutivo.pptx", pptx)
        archive.writestr(f"{base}_blockers.xlsx", xlsx)
    return buffer.getvalue(), f"{base}_pack.zip"


def aggregate_execution_issues(
    filter_id: str,
    swf: SwfDef,
    issues: list[dict[str, Any]] | None = None,
    grouped: dict[str, list[dict[str, Any]]] | None = None,
) -> ExecutionMetrics:
    buckets = grouped
    if buckets is None:
        buckets = {program.program_key.upper(): [] for program in swf.programs}
        for issue in issues or []:
            key = _project_key(issue)
            if key in buckets:
                buckets[key].append(issue)
    programs: list[ExecutionProgramMetrics] = []
    blockers: list[ExecutionBlockerRow] = []
    for program in swf.programs:
        rows = buckets[program.program_key]
        if not rows:
            continue
        blocker = 0
        for issue in rows:
            if not is_blocker_priority(_priority_name(issue)):
                continue
            if is_closed_status(_status_name(issue), _status_category_key(issue)):
                continue
            blocker += 1
            status_changed_at, status_from, status_to = _last_status_change(issue)
            last_comment_at, last_comment_author = _last_comment(issue)
            blockers.append(
                ExecutionBlockerRow(
                    key=str(issue.get("key") or "").strip().upper(),
                    summary=_summary(issue),
                    status=_status_name(issue),
                    program_key=program.program_key,
                    display_name=program.display_name,
                    issue_type=_issuetype_name(issue),
                    priority=_priority_name(issue),
                    created=_created_at(issue),
                    principal=_principal_key(issue),
                    status_changed_at=status_changed_at,
                    status_changed_from=status_from,
                    status_changed_to=status_to,
                    last_comment_at=last_comment_at,
                    last_comment_author=last_comment_author,
                    nested_issue_keys=_nested_issue_keys(issue),
                )
            )
        programs.append(
            ExecutionProgramMetrics(
                program_key=program.program_key,
                display_name=program.display_name,
                total=len(rows),
                blocker=blocker,
                non_blocker=len(rows) - blocker,
            )
        )
    blockers.sort(key=lambda row: (row.display_name, row.key))
    return ExecutionMetrics(
        filter_id=filter_id,
        issue_count=sum(row.total for row in programs),
        programs=programs,
        blockers=blockers,
    )


def build_sprint_testing(sprint_id: str, swf_id: str) -> SprintTestingRead:
    sprint, swf = _resolve_sprint_swf(sprint_id, swf_id)
    if not sprint.filter_id:
        raise SprintTestingConfigError(
            f"{sprint.label} aún no tiene un Saved Filter configurado."
        )
    issues = fetch_raw_issues_by_filter(sprint.filter_id, _ISSUE_FIELDS)
    payload = aggregate_issues(sprint.id, sprint.label, sprint.filter_id, swf, issues)
    if sprint_device_filters(sprint.id) or sprint.execution_filter_id:
        label, grouped = collect_execution_issues(sprint, swf)
        payload.execution = aggregate_execution_issues(label, swf, grouped=grouped)
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
