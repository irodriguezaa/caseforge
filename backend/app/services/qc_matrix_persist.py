"""Persist the 2B matrix selection as Release test cases.

Does not generate or replace RN cases. Does not compare them with the RN (that is 2C).
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.release import Release
from app.models.test_case import TestCase, TestCasePriority, TestCaseStatus, TestCaseType
from app.models.test_step import TestStep
from app.services.qc_matrix_selection import select_be_matrix_cases, select_matrix_cases

MATRIX_SOURCE = "qc_matrix"
SCOPE_PREFIX = {
    "Regresivo": "RG",
    "Smoke Test": "SM",
    "No Afectación": "NF",
    "Regresión completa": "RC",
    "Pruebas Acotadas": "PA",
}
_STEP_NUMBER = re.compile(r"^\d+[\.\)\-]\s*")


def persist_selected_matrix_cases(db: Session, release: Release) -> int:
    """Create or refresh matrix test cases for the Release scope. Returns how many exist afterwards."""
    if release.operativa_release_id is not None:
        return 0
    prefix = SCOPE_PREFIX.get((release.validation_type or "").strip())
    if prefix is None:
        return 0
    raw = None
    if release.analyses:
        stored = release.analyses[0].raw_analysis
        raw = stored if isinstance(stored, dict) else None
    is_be = release.be_release_id is not None or (release.platform or "").strip() == "BE"
    if is_be:
        preview = select_be_matrix_cases(
            db,
            validation_type=release.validation_type,
            touched_modules=release.qc_matrix_touched_modules,
            template_values=release.qc_matrix_template_values,
            raw_analysis=raw,
            pinned_version_id=None,
        )
    else:
        preview = select_matrix_cases(
            db,
            platform=release.platform,
            validation_type=release.validation_type,
            touched_modules=release.qc_matrix_touched_modules,
            template_values=release.qc_matrix_template_values,
            raw_analysis=raw,
            pinned_version_id=release.qc_matrix_version_id,
        )
    existing = list(
        db.execute(
            select(TestCase)
            .where(TestCase.release_id == release.id, TestCase.source_type == MATRIX_SOURCE)
            .options(selectinload(TestCase.steps))
        ).scalars().all()
    )
    # A scope change drops the previous prefix. Unexecuted rows from that scope are removed
    # and created again with the new prefix. Executed rows stay, even when the prefix differs.
    kept: list[TestCase] = []
    for row in existing:
        if row.status == TestCaseStatus.UNEXECUTED and _label_prefix(row.test_case_id) != prefix:
            db.delete(row)
            continue
        kept.append(row)
    existing = kept
    by_identity = {row.group_id: row for row in existing if row.group_id}
    used_ids = list(
        db.execute(select(TestCase.test_case_id).where(TestCase.release_id == release.id)).scalars().all()
    )
    wanted: set[str] = set()
    for item in preview["cases"]:
        identity = _identity(item, include_device=is_be)
        wanted.add(identity)
        current = by_identity.get(identity)
        if current is None:
            label = _next_label(prefix, used_ids)
            used_ids.append(label)
            created = _build(release.id, label, identity, item, preview, release.cluster, include_device=is_be)
            db.add(created)
            continue
        if current.status == TestCaseStatus.UNEXECUTED:
            _apply(current, item, preview, release.cluster, include_device=is_be)
            _replace_steps(db, current, item)
    for row in existing:
        if row.group_id not in wanted and row.status == TestCaseStatus.UNEXECUTED:
            db.delete(row)
    db.flush()
    return len(wanted)


def _identity(item: dict, *, include_device: bool = False) -> str:
    base = (item.get("base_id") or "sin-id").strip()
    provider = (item.get("provider") or "").strip()
    if not include_device:
        return f"{base}|{provider}"[:80]
    device = (item.get("device_code") or item.get("platform") or "").strip()
    return f"{base}|{provider}|{device}"[:80]


def _label_prefix(test_case_id: str) -> str:
    match = re.match(r"^([A-Za-z]+)-\d+$", (test_case_id or "").strip())
    return match.group(1).upper() if match else ""


def _next_label(prefix: str, used_ids: list[str]) -> str:
    pattern = re.compile(rf"^{prefix}-(\d+)$", re.IGNORECASE)
    highest = 0
    for label in used_ids:
        match = pattern.match((label or "").strip())
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{prefix}-{highest + 1:03d}"


def _build(
    release_id: int,
    label: str,
    identity: str,
    item: dict,
    preview: dict,
    cluster: str | None,
    *,
    include_device: bool = False,
) -> TestCase:
    case = TestCase(
        release_id=release_id,
        test_case_id=label,
        component="General",
        test_case_name="Caso de matriz",
        priority=_priority(item.get("severity")),
        test_type=TestCaseType.FUNCTIONAL,
        status=TestCaseStatus.UNEXECUTED,
        generated_by_engine=False,
        source_type=MATRIX_SOURCE,
        group_id=identity,
        estimation_hours=None,
    )
    _apply(case, item, preview, cluster, include_device=include_device)
    case.steps = _step_rows(item)
    return case


def _apply(
    case: TestCase,
    item: dict,
    preview: dict,
    cluster: str | None,
    *,
    include_device: bool = False,
) -> None:
    title = _title(item)
    users = [str(value) for value in (item.get("user_types") or []) if str(value).strip()]
    case.component = ((item.get("module_name") or item.get("module_key") or "General").strip())[:150]
    case.test_case_name = title[:250]
    case.description = title
    case.user_type = ", ".join(users)[:100] or None
    case.priority = _priority(item.get("severity"))
    case.test_type = TestCaseType.FUNCTIONAL
    case.technical_story = ((item.get("base_id") or "").strip() or None)
    case.test_data = _precondition(item, users, cluster)
    case.scenario_origin = _trace(item, preview)
    case.group_id = _identity(item, include_device=include_device)
    case.source_type = MATRIX_SOURCE
    case.generated_by_engine = False
    case.estimation_hours = None
    if include_device:
        device = (item.get("platform") or item.get("device_code") or "").strip()
        case.device = device[:80] or None


def _title(item: dict) -> str:
    title = (item.get("title") or "Caso de matriz").strip()
    note = (item.get("device_note") or "").strip()
    if note and note.casefold() not in title.casefold():
        title = f"{title} ({note})"
    return title


def _precondition(item: dict, users: list[str], cluster: str | None) -> str:
    parts: list[str] = []
    if users:
        parts.append("Tipo de usuario: " + ", ".join(users))
    parts.append("Cluster: " + ((cluster or "").strip() or "—"))
    provider = (item.get("provider") or "").strip()
    if provider:
        parts.append(f"Proveedor: {provider}")
    device = (item.get("device_code") or item.get("platform") or "").strip()
    if device:
        parts.append(f"Dispositivo: {device}")
    return "Precondición: " + " · ".join(parts)


def _trace(item: dict, preview: dict) -> str:
    code = item.get("matrix_code") or preview.get("matrix_code") or "matriz"
    version = item.get("matrix_version") or preview.get("matrix_version") or "sin versión"
    base = (item.get("base_id") or "sin id").strip()
    device = (item.get("device_code") or "").strip()
    suffix = f" · {device}" if device else ""
    return f"Matriz {code} {version} · id base {base}{suffix}"


def _priority(severity: str | None) -> TestCasePriority:
    if (severity or "").strip().casefold() == "blocker":
        return TestCasePriority.BLOCKER
    return TestCasePriority.CRITICAL


def _replace_steps(db: Session, case: TestCase, item: dict) -> None:
    for step in list(case.steps):
        db.delete(step)
    db.flush()
    case.steps = _step_rows(item)


def _step_rows(item: dict) -> list[TestStep]:
    actions = _split_steps(item.get("steps") or "")
    expected = (item.get("expected") or "").strip()
    title = (item.get("title") or "el caso").strip()
    if not actions:
        return [TestStep(step_number=1, test_step=f"Ejecutar: {title}", expected_result=expected)]
    return [
        TestStep(
            step_number=index,
            test_step=action,
            expected_result=expected if index == len(actions) else "—",
        )
        for index, action in enumerate(actions, start=1)
    ]


def _split_steps(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return []
    if not any(_STEP_NUMBER.match(line) for line in lines):
        return [" ".join(lines)]
    grouped: list[list[str]] = []
    for line in lines:
        if _STEP_NUMBER.match(line):
            grouped.append([_STEP_NUMBER.sub("", line).strip() or line])
        elif grouped:
            grouped[-1].append(line)
        else:
            grouped.append([line])
    return [" ".join(part for part in group if part) for group in grouped]
