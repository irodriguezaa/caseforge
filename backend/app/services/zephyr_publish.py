"""Publish persisted Test Cases to the Jira QCO Test issue type.

QCO_ZEPHYR_PUBLISH — parked until QC defines Zephyr format. UI is hidden
(SHOW_QCO_ZEPHYR_PUBLISH). Keep this module, mapping, and POST /publish-qco.

This is the live destination available with current credentials. Zephyr Scale Cloud
(/v2) requires a Scale access token and is not configured; QCO/Test is the QC project
issue type that accepts Test cases.

Does not rebuild coverage, merge TCs, or mutate TestCase/TestStep rows.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.test_case import TestCase, TestCasePriority
from app.models.test_case_publication import TestCasePublication
from app.services.jira_client import JiraNotConfiguredError, _client
from app.services.zephyr_mapping import pack_traceability_description, preview_zephyr_rows

DESTINATION = "QCO"
ISSUE_TYPE = "Test"
MARKER_PREFIX = "CaseForgeID:"
MAX_ATTEMPTS = 2

_PRIORITY_TO_JIRA_ID = {
    TestCasePriority.CRITICAL.value: "2",  # Crítica
    TestCasePriority.BLOCKER.value: "1",  # Supone un impedimento
}


@dataclass
class PublishRecord:
    caseforge_id: str
    zephyr_id: str | None
    brf: str
    hn: str
    device_channel: str
    name: str
    steps: int
    status: str
    resultado: str
    detail: str = ""


def fingerprint(case: TestCase) -> str:
    steps = sorted(case.steps, key=lambda item: item.step_number)
    parts = [
        case.test_case_id,
        case.test_case_name or "",
        case.description or "",
        case.test_data or "",
        str(len(steps)),
    ]
    for step in steps:
        parts.append(f"{step.step_number}|{step.test_step}|{step.expected_result}")
    return "\n".join(parts)


def _project_key() -> str:
    return os.getenv("ZEPHYR_PROJECT_KEY", DESTINATION)


def _enum(value: object) -> str:
    return value.value if hasattr(value, "value") else str(value or "")


def _hn(case: TestCase) -> str:
    for line in (case.test_data or "").splitlines():
        if line.startswith("HN:"):
            return line.split(":", 1)[1].strip()
    return ""


def _device_channel(case: TestCase) -> str:
    if case.device:
        return case.device
    for line in (case.test_data or "").splitlines():
        if line.startswith("Canal:"):
            return line.split(":", 1)[1].strip()
    return "—"


def _adf_from_text(text: str) -> dict:
    content: list[dict] = []
    for line in (text or "").split("\n"):
        if line:
            content.append(
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": line[:30000]}],
                }
            )
        else:
            content.append({"type": "paragraph"})
    if not content:
        content.append({"type": "paragraph", "content": [{"type": "text", "text": " "}]})
    return {"type": "doc", "version": 1, "content": content}


def build_remote_description(case: TestCase) -> str:
    rows = preview_zephyr_rows(case)
    description = rows[0]["Description"] if rows else (case.description or "")
    step_block = ["", "Steps (1:1 con Expected Result):"]
    for row in rows:
        step_block.append(f"Step {row['Step']}: {row['Test Step']}")
        step_block.append(f"Expected {row['Step']}: {row['Expected Result']}")
    header = [
        f"{MARKER_PREFIX}{case.test_case_id}",
        f"Component: {case.component}",
        f"CaseForge Test Type: {_enum(case.test_type)}",
        f"CaseForge Status: {_enum(case.status)}",
        f"CaseForge Priority: {_enum(case.priority)}",
        "",
    ]
    return "\n".join(header) + description + "\n" + "\n".join(step_block)


def _priority_ids_from_jira(client: httpx.Client) -> dict[str, str]:
    """Map CaseForge priorities to this Jira site's ids. Names are locale-specific."""
    mapped = dict(_PRIORITY_TO_JIRA_ID)
    try:
        response = client.get("/rest/api/3/priority")
    except Exception:
        return mapped
    if response.status_code != 200:
        return mapped
    payload = response.json()
    if not isinstance(payload, list):
        return mapped
    for item in payload:
        name = (item.get("name") or "").lower()
        pid = str(item.get("id") or "")
        if not pid:
            continue
        if "crítica" in name or name in {"critical", "highest"}:
            mapped[TestCasePriority.CRITICAL.value] = pid
        if "impedimento" in name or "blocker" in name:
            mapped[TestCasePriority.BLOCKER.value] = pid
    return mapped


def _jira_priority_id(case: TestCase, catalog: dict[str, str] | None = None) -> str:
    table = catalog or _PRIORITY_TO_JIRA_ID
    return table.get(_enum(case.priority), table.get(TestCasePriority.CRITICAL.value, "2"))


def _create_issue(
    client: httpx.Client,
    case: TestCase,
    account_id: str | None = None,
    priority_ids: dict[str, str] | None = None,
) -> tuple[str | None, str]:
    fields = {
        "project": {"key": _project_key()},
        "issuetype": {"name": ISSUE_TYPE},
        "summary": (case.test_case_name or case.test_case_id)[:255],
        "description": _adf_from_text(build_remote_description(case)),
        "priority": {"id": _jira_priority_id(case, priority_ids)},
    }
    if account_id:
        fields["reporter"] = {"accountId": account_id}
    body = {"fields": fields}
    last_error = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        response = client.post("/rest/api/3/issue", json=body)
        if response.status_code in {200, 201}:
            key = response.json().get("key")
            return key, "created"
        if response.status_code == 429 and attempt < MAX_ATTEMPTS:
            last_error = f"HTTP 429 {response.text[:300]}"
            continue
        last_error = f"HTTP {response.status_code} {response.text[:500]}"
        return None, last_error
    return None, last_error


def publish_cases(db: Session, cases: list[TestCase]) -> list[PublishRecord]:
    existing = {
        row.test_case_id: row
        for row in db.scalars(
            select(TestCasePublication).where(
                TestCasePublication.test_case_id.in_([case.id for case in cases]),
                TestCasePublication.destination == DESTINATION,
            )
        ).all()
    }
    records: list[PublishRecord] = []
    try:
        client_cm = _client(timeout=60.0)
    except JiraNotConfiguredError as exc:
        for case in cases:
            records.append(
                _record(case, None, "error", str(exc))
            )
        return records

    with client_cm as client:
        myself = client.get("/rest/api/3/myself")
        account_id = myself.json().get("accountId") if myself.status_code == 200 else None
        priority_ids = _priority_ids_from_jira(client)
        for case in cases:
            prior = existing.get(case.id)
            if prior and prior.result == "created" and prior.remote_key:
                records.append(_record(case, prior.remote_key, "duplicate", "Ya publicado; no se recreó."))
                continue
            key, detail = _create_issue(client, case, account_id, priority_ids)
            if key:
                _upsert(db, case.id, key, "created", None)
                db.commit()
                records.append(_record(case, key, "created", "created"))
            else:
                _upsert(db, case.id, None, "error", detail)
                db.commit()
                records.append(_record(case, None, "error", detail))
    return records


def _upsert(db: Session, test_case_pk: int, remote_key: str | None, result: str, detail: str | None) -> None:
    row = db.scalar(
        select(TestCasePublication).where(
            TestCasePublication.test_case_id == test_case_pk,
            TestCasePublication.destination == DESTINATION,
        )
    )
    if row is None:
        db.add(
            TestCasePublication(
                test_case_id=test_case_pk,
                destination=DESTINATION,
                remote_key=remote_key,
                result=result,
                detail=(detail or "")[:2000] or None,
            )
        )
        return
    row.remote_key = remote_key or row.remote_key
    row.result = result
    row.detail = (detail or "")[:2000] or None


def _record(case: TestCase, remote: str | None, resultado: str, detail: str) -> PublishRecord:
    return PublishRecord(
        caseforge_id=case.test_case_id,
        zephyr_id=remote,
        brf=case.component,
        hn=_hn(case),
        device_channel=_device_channel(case),
        name=case.test_case_name,
        steps=len(case.steps),
        status=_enum(case.status),
        resultado=resultado,
        detail=detail,
    )


def load_engine_cases(db: Session, release_id: int) -> list[TestCase]:
    """All engine TCs for a Release. No BRF allowlist — any new BRF is included."""
    return list(
        db.scalars(
            select(TestCase)
            .where(
                TestCase.release_id == release_id,
                TestCase.generated_by_engine.is_(True),
            )
            .options(selectinload(TestCase.steps))
            .order_by(TestCase.test_case_id)
        ).all()
    )


def load_official_cases(db: Session, release_id: int, brfs: set[str] | None = None) -> list[TestCase]:
    cases = load_engine_cases(db, release_id)
    if not brfs:
        return cases
    return [case for case in cases if case.component in brfs]
