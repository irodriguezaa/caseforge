"""Release Apps EPC identity: RN is scope, TCs are the result.

Stories may feed Gherkin/analysis. They never become the visible EPC key.
0 TCs never remove an RN functionality from the spine.
"""

from __future__ import annotations

from typing import Any

from app.schemas.case_generation import CoverageUnit, GeneratedCaseCandidate

ORPHAN_EPC = "Sin EPC"
COVERAGE_STATUSES = ("sin_gherkin", "sin_casos", "parcial", "cubierta")


def normalize_key(raw: Any) -> str:
    return str(raw or "").strip().upper()


def split_issue_keys(raw: Any) -> list[str]:
    keys: list[str] = []
    for part in str(raw or "").split("|"):
        key = normalize_key(part)
        if key and key not in keys:
            keys.append(key)
    return keys


def rn_keys_from_tickets(tickets: dict[str, list[tuple[str, str]]] | None) -> list[str]:
    keys: list[str] = []
    for ticket_id, _text in (tickets or {}).get("functionality", []):
        key = normalize_key(ticket_id)
        if key and key not in keys:
            keys.append(key)
    return keys


def rn_keys_from_normalized(raw_analysis: Any) -> list[str]:
    if not isinstance(raw_analysis, dict):
        return []
    normalized = raw_analysis.get("normalized")
    if not isinstance(normalized, dict):
        return []
    epics = normalized.get("technical_epics")
    if not isinstance(epics, list):
        return []
    keys: list[str] = []
    for item in epics:
        key = ""
        if isinstance(item, dict):
            key = normalize_key(item.get("id") or item.get("key"))
        else:
            key = normalize_key(getattr(item, "id", None))
        if key and key not in keys:
            keys.append(key)
    return keys


def story_to_rn_map(
    artifacts: list[dict[str, Any]] | None,
    rn_keys: list[str] | set[str],
) -> dict[str, str]:
    """Child Jira key → RN EPC parent. Parent must be in the RN spine."""
    allowed = {normalize_key(key) for key in rn_keys if normalize_key(key)}
    mapping: dict[str, str] = {}
    for artifact in artifacts or []:
        if not isinstance(artifact, dict):
            continue
        parent = normalize_key(artifact.get("key"))
        if not parent or parent not in allowed:
            continue
        mapping[parent] = parent
        for child in artifact.get("children") or []:
            if not isinstance(child, dict):
                continue
            child_key = normalize_key(child.get("key"))
            parent_field = normalize_key(child.get("parent_key"))
            if not child_key:
                continue
            if parent_field and parent_field != parent:
                continue
            mapping[child_key] = parent
    return mapping


def resolve_rn_epic(
    raw: Any,
    rn_keys: list[str] | set[str],
    story_map: dict[str, str] | None = None,
) -> str | None:
    """Map a stored key to the RN EPC. None = orphan (do not invent)."""
    allowed = [normalize_key(key) for key in rn_keys if normalize_key(key)]
    allowed_set = set(allowed)
    mapping = story_map or {}
    for part in split_issue_keys(raw):
        if part in allowed_set:
            return part
        parent = mapping.get(part)
        if parent and parent in allowed_set:
            return parent
    return None


def coverage_status(*, ag_total: int, ag_covered: int, tc_count: int) -> str:
    pending = max(0, int(ag_total) - int(ag_covered))
    if int(tc_count) <= 0 and int(ag_total) <= 0:
        return "sin_gherkin"
    if int(tc_count) <= 0:
        return "sin_casos"
    if pending > 0:
        return "parcial"
    return "cubierta"


def stamp_candidate_identity(
    candidate: GeneratedCaseCandidate,
    rn_keys: list[str],
    story_map: dict[str, str],
) -> GeneratedCaseCandidate:
    allowed = {normalize_key(key) for key in rn_keys}
    func_parts = split_issue_keys(candidate.related_functionality)
    jira_parts = split_issue_keys(candidate.related_jira)
    rn_found: list[str] = []
    stories: list[str] = []
    for part in [*func_parts, *jira_parts]:
        mapped = resolve_rn_epic(part, rn_keys, story_map)
        if mapped and mapped not in rn_found:
            rn_found.append(mapped)
        if part not in allowed and part in story_map and part not in stories:
            stories.append(part)
        elif part not in allowed and mapped and part not in stories:
            stories.append(part)
    candidate.related_functionality = " | ".join(rn_found) if rn_found else None
    if stories:
        candidate.related_jira = " | ".join(stories)
    elif jira_parts:
        candidate.related_jira = " | ".join(jira_parts)
    elif rn_found:
        candidate.related_jira = " | ".join(rn_found)
    return candidate


def stamp_candidates(
    candidates: list[GeneratedCaseCandidate],
    rn_keys: list[str],
    artifacts: list[dict[str, Any]] | None,
) -> list[GeneratedCaseCandidate]:
    mapping = story_to_rn_map(artifacts, rn_keys)
    for candidate in candidates:
        stamp_candidate_identity(candidate, rn_keys, mapping)
    return candidates


def build_rn_scope_coverage(
    *,
    rn_keys: list[str],
    artifacts: list[dict[str, Any]] | None,
    inventory: list[CoverageUnit],
    covered_ids: list[str] | set[str],
    candidates: list[GeneratedCaseCandidate],
) -> dict[str, Any]:
    mapping = story_to_rn_map(artifacts, rn_keys)
    covered_set = {str(cid) for cid in covered_ids}
    units_by_rn: dict[str, list[CoverageUnit]] = {key: [] for key in rn_keys}
    for unit in inventory:
        rn_key = resolve_rn_epic(unit.rn_key or unit.artifact_key, rn_keys, mapping)
        if rn_key:
            units_by_rn.setdefault(rn_key, []).append(unit)
    stories_by_rn: dict[str, list[str]] = {key: [] for key in rn_keys}
    for artifact in artifacts or []:
        parent = normalize_key(artifact.get("key") if isinstance(artifact, dict) else "")
        if parent not in stories_by_rn:
            continue
        for child in artifact.get("children") or []:
            if not isinstance(child, dict):
                continue
            child_key = normalize_key(child.get("key"))
            issuetype = str(child.get("issuetype") or "").lower()
            if child_key and "story" in issuetype and child_key not in stories_by_rn[parent]:
                stories_by_rn[parent].append(child_key)
    tcs_by_rn: dict[str, int] = {key: 0 for key in rn_keys}
    for candidate in candidates:
        mapped = resolve_rn_epic(
            candidate.related_functionality or candidate.related_jira, rn_keys, mapping
        )
        if mapped:
            tcs_by_rn[mapped] = tcs_by_rn.get(mapped, 0) + 1
    epics: list[dict[str, Any]] = []
    for key in rn_keys:
        units = units_by_rn.get(key) or []
        covered_units = [unit.coverage_id for unit in units if unit.coverage_id in covered_set]
        pending_units = [unit.coverage_id for unit in units if unit.coverage_id not in covered_set]
        tc_count = tcs_by_rn.get(key, 0)
        epics.append(
            {
                "rn_key": key,
                "stories": stories_by_rn.get(key) or [],
                "coverage_units": [unit.coverage_id for unit in units],
                "covered_units": covered_units,
                "pending_units": pending_units,
                "test_cases": tc_count,
                "estado": coverage_status(
                    ag_total=len(units),
                    ag_covered=len(covered_units),
                    tc_count=tc_count,
                ),
            }
        )
    return {"epics": epics, "story_to_epic": mapping}


def merge_coverage_into_raw_analysis(raw_analysis: Any, coverage: dict[str, Any]) -> dict[str, Any]:
    payload = dict(raw_analysis) if isinstance(raw_analysis, dict) else {}
    payload["rn_scope_coverage"] = coverage
    return payload


def case_scope_key(
    *,
    technical_epic: Any = None,
    component: Any = None,
    hn_source: Any = None,
    technical_story: Any = None,
    rn_keys: list[str],
    story_map: dict[str, str],
) -> str | None:
    for raw in (technical_epic, component, hn_source, technical_story):
        mapped = resolve_rn_epic(raw, rn_keys, story_map)
        if mapped:
            return mapped
    return None


def left_join_epic_progress(
    *,
    rn_keys: list[str],
    cases: list[Any],
    story_map: dict[str, str] | None = None,
    coverage: dict[str, Any] | None = None,
    hours_of=None,
    is_executed=None,
) -> list[dict[str, Any]]:
    """RN spine LEFT JOIN TCs. Preserves RN order. Orphans are not added as EPCs."""
    mapping = story_map or {}
    if coverage and isinstance(coverage.get("story_to_epic"), dict):
        mapping = {**coverage["story_to_epic"], **mapping}
    coverage_by_key = {}
    if coverage:
        for row in coverage.get("epics") or []:
            if isinstance(row, dict) and row.get("rn_key"):
                coverage_by_key[normalize_key(row["rn_key"])] = row
    grouped: dict[str, dict[str, float]] = {
        key: {"total": 0, "executed": 0, "hours": 0.0} for key in rn_keys
    }
    orphan_stats = {"total": 0, "executed": 0, "hours": 0.0}
    for case in cases:
        hours = float(hours_of(case) if hours_of else 0.0)
        executed = bool(is_executed(case)) if is_executed else False
        mapped = case_scope_key(
            technical_epic=getattr(case, "technical_epic", None)
            if not isinstance(case, dict)
            else case.get("technical_epic"),
            component=getattr(case, "component", None)
            if not isinstance(case, dict)
            else case.get("component"),
            hn_source=getattr(case, "hn_source", None) if not isinstance(case, dict) else case.get("hn_source"),
            technical_story=getattr(case, "technical_story", None)
            if not isinstance(case, dict)
            else case.get("technical_story"),
            rn_keys=rn_keys,
            story_map=mapping,
        )
        bucket = grouped.get(mapped) if mapped else None
        if bucket is None:
            orphan_stats["total"] += 1
            if executed:
                orphan_stats["executed"] += 1
            orphan_stats["hours"] += hours
            continue
        bucket["total"] += 1
        if executed:
            bucket["executed"] += 1
        bucket["hours"] += hours
    rows: list[dict[str, Any]] = []
    for key in rn_keys:
        stats = grouped[key]
        total = int(stats["total"])
        executed = int(stats["executed"])
        percent = 0.0 if total == 0 else round(executed * 1000 / total) / 10
        snap = coverage_by_key.get(key) or {}
        ag_total = len(snap.get("coverage_units") or [])
        ag_covered = len(snap.get("covered_units") or [])
        rows.append(
            {
                "key": key,
                "total": total,
                "executed": executed,
                "percent": percent,
                "hours": round(stats["hours"] * 10) / 10,
                "stories": list(snap.get("stories") or []),
                "estado": coverage_status(ag_total=ag_total, ag_covered=ag_covered, tc_count=total),
                "orphan": False,
            }
        )
    if orphan_stats["total"]:
        total = int(orphan_stats["total"])
        executed = int(orphan_stats["executed"])
        rows.append(
            {
                "key": ORPHAN_EPC,
                "total": total,
                "executed": executed,
                "percent": 0.0 if total == 0 else round(executed * 1000 / total) / 10,
                "hours": round(orphan_stats["hours"] * 10) / 10,
                "stories": [],
                "estado": "sin_casos" if total == 0 else "parcial",
                "orphan": True,
            }
        )
    return rows


def remap_case_fields(
    *,
    technical_epic: str | None,
    technical_story: str | None,
    component: str | None,
    rn_keys: list[str],
    story_map: dict[str, str],
    justification: str | None = None,
) -> dict[str, str | None] | None:
    """If technical_epic is a child of an RN EPC, move it to the parent. Else None (no change)."""
    current = normalize_key(split_issue_keys(technical_epic)[0] if split_issue_keys(technical_epic) else "")
    if not current:
        current = normalize_key(split_issue_keys(component)[0] if split_issue_keys(component) else "")
    if not current:
        return None
    if current in {normalize_key(key) for key in rn_keys}:
        return None
    parent = story_map.get(current)
    if not parent or parent not in {normalize_key(key) for key in rn_keys}:
        return None
    stories = split_issue_keys(technical_story)
    if current not in stories:
        stories.insert(0, current)
    note = f"Remap EPC: {current} → {parent} (Story hija; alcance RN)."
    just = justification or ""
    if note not in just:
        just = f"{just} {note}".strip()
    new_component = component
    if normalize_key(split_issue_keys(component)[0] if split_issue_keys(component) else "") == current:
        new_component = parent
    return {
        "technical_epic": parent,
        "technical_story": " | ".join(stories),
        "component": new_component,
        "justification": just,
    }
