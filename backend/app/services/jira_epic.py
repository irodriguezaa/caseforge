"""Create one QCO Epic from a release that already has test cases.

Tasks and subtasks are not created here. The Epic title is
PROGRAMA | VERSIÓN | TIPO.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.release import Release
from app.models.release_analysis import ReleaseAnalysis
from app.models.test_case import TestCase
from app.schemas.release import ActivityType, EnvironmentName
from app.services.jira_client import JiraApiError, _client

PROJECT_KEY = "QCO"
ISSUE_EPIC = "Epic"
PRIORITY_NAME = "Importante"
ACTIVITY_TITLE: dict[str, str] = {
    "HotFix": "HOTFIX",
    "Exc": "EXC",
    "Mantenimiento": "MANTENIMIENTO",
    "Release": "RELEASE",
}
_DEVICE_PROGRAM = {
    "WEB": "WEBCL",
    "WIN/XBOX": "WINCL",
}
_KEY_RE = re.compile(r"^([A-Z][A-Z0-9]+)-\d+$")


class JiraEpicError(Exception):
    """The release is not ready to open an Epic."""


@dataclass(frozen=True)
class EpicDraft:
    release_id: int
    summary: str
    description: str
    activity_type: str
    environment: str


@dataclass(frozen=True)
class EpicResult:
    already_existed: bool
    key: str
    summary: str
    activity_type: str
    environment: str


def program_code(platform: str, keys: list[str]) -> str:
    counts: dict[str, int] = {}
    for raw in keys:
        match = _KEY_RE.match(str(raw or "").strip().upper())
        if match:
            prefix = match.group(1)
            counts[prefix] = counts.get(prefix, 0) + 1
    if counts:
        return max(counts.items(), key=lambda item: (item[1], item[0]))[0]
    fallback = _DEVICE_PROGRAM.get((platform or "").strip())
    if fallback:
        return fallback
    raise JiraEpicError(
        "No hay un programa (WEBCL, WINCL) en las EPC de esta release."
    )


def epic_summary(program: str, version: str, activity_type: str) -> str:
    kind = ACTIVITY_TITLE.get(activity_type)
    if kind is None:
        raise JiraEpicError("El tipo debe ser HotFix, Exc, Mantenimiento o Release.")
    version_text = re.sub(r"\s+", " ", (version or "").strip())
    if not version_text:
        raise JiraEpicError("La release no tiene versión.")
    return f"{program} | {version_text} | {kind}"


def epic_description(
    *,
    device: str,
    version: str,
    environment: str,
    validation_type: str | None,
    rn_filename: str | None,
    functionalities: list[tuple[str, str]],
    qc_bugs: list[tuple[str, str]],
) -> str:
    scope = (validation_type or "").strip() or "Sin tipo de prueba"
    rn = (rn_filename or "").strip()
    return "\n".join(
        [
            "Objetivo",
            "",
            f"Liberar {device} versión {version} para Claro Video",
            "",
            "Contexto",
            "",
            f"El Release Note corresponde a la liberación a producción de la aplicación Clarovideo {device}.",
            f"Incluye funcionalidades nuevas para el entorno {environment}.",
            f"La versión indicada es {version} y requiere aprobación.",
            "",
            "Alcance",
            "",
            "Listado de EPCs (funcionalidades)",
            *_lines(functionalities, "Sin EPC en el RN."),
            "",
            "Listado de QC Bugs",
            *_lines(qc_bugs, "Sin bugs QC en el RN."),
            "",
            f"Tipo de prueba: {scope}",
            "",
            "Otra información",
            "",
            f"RN: {rn}".rstrip(),
            f"Entorno: {environment}",
            f"Versión: {version}",
        ]
    )


def draft_for_release(
    db: Session,
    release: Release,
    activity_type: ActivityType | None,
    environment: EnvironmentName | None,
) -> EpicDraft:
    chosen_type = activity_type or release.activity_type
    chosen_env = environment or release.environment
    if chosen_type not in ACTIVITY_TITLE:
        raise JiraEpicError("Elige el Tipo: HotFix, Exc, Mantenimiento o Release.")
    if chosen_env not in {"BERC", "FEHF", "OPER", "PROD"}:
        raise JiraEpicError("Elige el Ambiente: BERC, FEHF, OPER o PROD.")

    case_count = db.scalar(
        select(func.count()).select_from(TestCase).where(TestCase.release_id == release.id)
    )
    if not case_count:
        raise JiraEpicError("Genera los casos de prueba antes de crear la EPC.")

    analysis = db.scalars(
        select(ReleaseAnalysis)
        .where(ReleaseAnalysis.release_id == release.id)
        .order_by(ReleaseAnalysis.created_at.desc())
    ).first()
    functionalities = _bucket(analysis, "technical_epics")
    bugs = _bucket(analysis, "qc_bugs") or _bucket(analysis, "qa_qc")
    keys = [key for key, _title in functionalities]
    if not keys:
        keys = _case_keys(db, release.id)
    version = re.sub(r"\s+", " ", (release.version or "").strip())
    summary = epic_summary(program_code(release.platform, keys), version, chosen_type)
    description = epic_description(
        device=release.platform,
        version=version,
        environment=chosen_env,
        validation_type=release.validation_type,
        rn_filename=analysis.pdf_filename if analysis is not None else None,
        functionalities=functionalities or [(key, "") for key in keys],
        qc_bugs=bugs,
    )
    if activity_type is not None:
        release.activity_type = activity_type
    if environment is not None:
        release.environment = environment
    return EpicDraft(
        release_id=release.id,
        summary=summary,
        description=description,
        activity_type=chosen_type,
        environment=chosen_env,
    )


def publish_epic(draft: EpicDraft) -> EpicResult:
    existing = _find_epic(draft.summary)
    if existing:
        return EpicResult(
            already_existed=True,
            key=existing,
            summary=draft.summary,
            activity_type=draft.activity_type,
            environment=draft.environment,
        )
    key = _create_issue(_fields(draft))
    return EpicResult(
        already_existed=False,
        key=key,
        summary=draft.summary,
        activity_type=draft.activity_type,
        environment=draft.environment,
    )


def _bucket(analysis: ReleaseAnalysis | None, name: str) -> list[tuple[str, str]]:
    if analysis is None or not isinstance(analysis.raw_analysis, dict):
        return []
    normalized = analysis.raw_analysis.get("normalized")
    if not isinstance(normalized, dict):
        return []
    rows = normalized.get(name)
    if not isinstance(rows, list):
        return []
    items: list[tuple[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = str(row.get("id") or row.get("key") or "").strip().upper()
        title = str(row.get("title") or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        items.append((key, title))
    return items


def _case_keys(db: Session, release_id: int) -> list[str]:
    rows = db.scalars(select(TestCase).where(TestCase.release_id == release_id)).all()
    keys: list[str] = []
    for row in rows:
        for raw in (row.technical_epic, row.component):
            for part in str(raw or "").split("|"):
                key = part.strip().upper()
                if _KEY_RE.match(key) and key not in keys:
                    keys.append(key)
    return keys


def _lines(items: list[tuple[str, str]], empty: str) -> list[str]:
    if not items:
        return [empty]
    lines: list[str] = []
    for key, title in items:
        rest = title
        upper = rest.upper()
        token = key.upper()
        for prefix in (f"{token}:", f"{token} -", f"{token}|", token):
            if upper.startswith(prefix):
                rest = rest[len(prefix) :].strip(" :-|")
                break
        text = f"- {key} {rest}".strip() if rest else f"- {key}"
        lines.append(text[:240])
    return lines


def _fields(draft: EpicDraft) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "project": {"key": PROJECT_KEY},
        "issuetype": {"name": ISSUE_EPIC},
        "summary": draft.summary,
        "priority": {"name": PRIORITY_NAME},
        "description": _adf(draft.description),
        "labels": ["qcpulse", f"qcpulse-r{draft.release_id}"],
    }
    account = _account_id()
    if account:
        fields["reporter"] = {"accountId": account}
    return fields


def _adf(text: str) -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            content.append({"type": "paragraph", "content": []})
            continue
        content.append({"type": "paragraph", "content": [{"type": "text", "text": line}]})
    if not content:
        content = [{"type": "paragraph", "content": [{"type": "text", "text": "QC Pulse"}]}]
    return {"type": "doc", "version": 1, "content": content}


def _jql_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _find_epic(summary: str) -> str | None:
    jql = (
        f"project = {PROJECT_KEY} AND issuetype = Epic AND summary = {_jql_quote(summary)} "
        "ORDER BY created DESC"
    )
    issues = _search(jql)
    return str(issues[0]["key"]) if issues else None


def _search(jql: str) -> list[dict[str, Any]]:
    with _client() as client:
        response = client.post(
            "/rest/api/3/search/jql",
            json={"jql": jql, "maxResults": 5, "fields": ["summary"]},
        )
    if response.status_code != 200:
        raise JiraApiError(response.status_code, response.text[:500])
    issues = response.json().get("issues") or []
    return issues if isinstance(issues, list) else []


def _create_issue(fields: dict[str, Any]) -> str:
    with _client() as client:
        response = client.post("/rest/api/3/issue", json={"fields": fields})
    if response.status_code not in (200, 201):
        raise JiraApiError(response.status_code, response.text[:800])
    key = str(response.json().get("key") or "")
    if not key:
        raise JiraApiError(response.status_code, "Jira no devolvió la key de la EPC.")
    return key


def _account_id() -> str | None:
    try:
        with _client() as client:
            response = client.get("/rest/api/3/myself")
    except Exception:
        return None
    if response.status_code != 200:
        return None
    account = response.json().get("accountId")
    return str(account) if account else None
