"""Persist engine candidates as Release TestCase/TestStep rows.

Does not change A–G classification or candidate generation. Release effort uses the homologated count-based QC formula, not per-case hours.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.test_case import TestCase, TestCasePriority, TestCaseStatus, TestCaseType
from app.models.test_step import TestStep
from app.schemas.case_generation import GeneratedCaseCandidate
from app.services.qc_effort import classify_complexity, estimate_release

_ID_NUMBER = re.compile(r"^(?:QC|TC)-(\d+)$", re.IGNORECASE)


def next_test_case_id(existing_ids: list[str]) -> str:
    highest = 0
    for label in existing_ids:
        match = _ID_NUMBER.match((label or "").strip())
        if match:
            highest = max(highest, int(match.group(1)))
    return f"QC-{highest + 1:03d}"


def _join_test_data(candidate: GeneratedCaseCandidate) -> str | None:
    parts: list[str] = []
    if candidate.mdp:
        parts.append(f"MDP: {candidate.mdp}")
    if candidate.test_data:
        text = candidate.test_data.strip()
        if text and text not in parts:
            parts.append(text)
    return "\n".join(parts) or None


def _audit_justification(candidate: GeneratedCaseCandidate) -> str:
    parts = [candidate.justification or ""]
    if candidate.priority_reason and candidate.priority_reason not in parts[0]:
        parts.append(candidate.priority_reason)
    if candidate.duplicate_status and candidate.duplicate_status != "UNIQUE":
        related = ", ".join((candidate.duplicate_with or [])[:8])
        parts.append(f"duplicateStatus={candidate.duplicate_status}; duplicateWith=[{related}]")
    if candidate.device_source and f"Fuente dispositivo: {candidate.device_source}" not in parts[0]:
        parts.append(f"Fuente dispositivo: {candidate.device_source}")
    if candidate.covers:
        parts.append("covers=" + ",".join(candidate.covers))
    return " ".join(part for part in parts if part).strip()



def _scenario_origin(candidate: GeneratedCaseCandidate) -> str | None:
    lines = [line.strip() for line in (candidate.evidence or "").splitlines() if line.strip()]
    return "\n".join(lines)[:8000] or None


def engine_cases_for_release(db: Session, release_id: int) -> list[TestCase]:
    stmt = (
        select(TestCase)
        .where(TestCase.release_id == release_id, TestCase.generated_by_engine.is_(True))
        .options(selectinload(TestCase.steps))
        .order_by(TestCase.test_case_id)
    )
    return list(db.execute(stmt).scalars().all())


def delete_engine_cases(db: Session, release_id: int) -> int:
    rows = engine_cases_for_release(db, release_id)
    count = len(rows)
    for row in rows:
        db.delete(row)
    if count:
        db.flush()
    return count


def summarize_cases(cases: list[TestCase]) -> dict[str, Any]:
    hours, days = estimate_release(len(cases))
    by_status: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    by_complexity: dict[str, int] = {}
    for row in cases:
        status = row.status.value if hasattr(row.status, "value") else str(row.status)
        priority = row.priority.value if hasattr(row.priority, "value") else str(row.priority)
        complexity = row.complexity or "—"
        by_status[status] = by_status.get(status, 0) + 1
        by_priority[priority] = by_priority.get(priority, 0) + 1
        by_complexity[complexity] = by_complexity.get(complexity, 0) + 1
    return {
        "test_case_count": len(cases),
        "estimation_hours": hours,
        "estimation_days": days,
        "by_status": by_status,
        "by_priority": by_priority,
        "by_complexity": by_complexity,
    }


def persist_candidates(
    db: Session,
    release_id: int,
    platform: str,
    candidates: list[GeneratedCaseCandidate],
) -> list[TestCase]:
    existing = list(
        db.execute(select(TestCase).where(TestCase.release_id == release_id)).scalars().all()
    )
    used_ids = [row.test_case_id for row in existing]
    created: list[TestCase] = []
    for candidate in candidates:
        complexity = classify_complexity(candidate)
        label = next_test_case_id(used_ids)
        used_ids.append(label)
        priority = (
            TestCasePriority.BLOCKER
            if candidate.priority == "BLOCKER"
            else TestCasePriority.CRITICAL
        )
        test_data = _join_test_data(candidate)
        test_case = TestCase(
            release_id=release_id,
            test_case_id=label,
            component=(candidate.component or candidate.related_functionality or platform or "General")[:150],
            test_case_name=candidate.name[:250],
            description=(candidate.description or "")[:8000] or None,
            user_type=(candidate.user_type or None),
            priority=priority,
            test_type=TestCaseType.FUNCTIONAL,
            status=TestCaseStatus.UNEXECUTED,
            test_data=test_data,
            requires_condition=bool(candidate.requires_condition),
            evidence=(candidate.evidence or "")[:16000] or None,
            justification=_audit_justification(candidate)[:4000] or None,
            technical_epic=(candidate.related_functionality or None),
            technical_story=(candidate.related_jira or None),
            scenario_origin=_scenario_origin(candidate),
            related_rn=(candidate.related_rn or None),
            confidence=candidate.confidence,
            complexity=complexity,
            generated_by_engine=True,
            ecosystem=(candidate.ecosystem or None),
            device=(candidate.device or None),
            device_source=(candidate.device_source or None),
            applicability_reason=(candidate.applicability_reason or None),
            duplicate_status=(candidate.duplicate_status or None),
            group_id=(candidate.group_id or None),
            hn_source=(candidate.hn_source or None),
        )
        steps = candidate.steps or []
        if not steps:
            test_case.steps = [
                TestStep(
                    step_number=1,
                    test_step="Ingresar a Claro video.",
                    expected_result="QC debe completar el criterio observable; no hay pasos ejecutables en la fuente.",
                )
            ]
        else:
            test_case.steps = [
                TestStep(
                    step_number=step.step_number or index,
                    test_step=step.action,
                    expected_result=step.expected_result,
                )
                for index, step in enumerate(steps, start=1)
            ]
        db.add(test_case)
        created.append(test_case)
    db.flush()
    return created
