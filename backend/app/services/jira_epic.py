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
from app.services.rn_storage import read_release_note_pdf

PROJECT_KEY = "QCO"
ISSUE_EPIC = "Epic"
# The scheme lists this priority as "Importante", but creating with the name is rejected.
# The id is what QCO accepts.
PRIORITY_ID = "3"
ACTIVITY_TITLE: dict[str, str] = {
    "HotFix": "HOTFIX",
    "Exc": "EXC",
    "Mantenimiento": "MANTENIMIENTO",
    "Release": "RELEASE",
}
_DEVICE_PROGRAM = {
    "WEB": "WEBCL",
    "ADT": "ADTCL",
    "FireTV": "ADTCL",
    "WIN/XBOX": "WINCL",
    "AAF Evolutivo": "STVCL",
    "AAF Legacy": "AAFCL",
    "IPTV AOSP": "AOSPCL",
    "iOS": "IOSPR",
    "tvOS": "TVOSPR",
    "ADR": "ADRPR",
    "Coship9085": "C9085PR",
    "STB IPTV": "ATSCL",
    "Roku": "ROKUPR",
    "STV Tata Samsung": "SCTCL",
    "STV Tata Hisense": "SCTCL",
    "STV Tata LG": "SCTCL",
    "STV Tata ADT": "SCTCL",
}
_PROGRAM_ASSIGNEE = {
    "WEBCL": "60be5d2ba01e11006ab15146",
    "ADTCL": "60be5d2ba01e11006ab15146",
    "WINCL": "60be5d2ba01e11006ab15146",
    "AAFCL": "625eec3bb8be7c006a447d99",
    "STVCL": "625eec3bb8be7c006a447d99",
    "AOSPCL": "625eec3bb8be7c006a447d99",
    "IOSPR": "5f6a0720f0d4010070378042",
    "TVOSPR": "5f6a0720f0d4010070378042",
    "ADRPR": "5a9d9b1fa3f5e92a7384b0ad",
    "C9085PR": "5a9d9b1fa3f5e92a7384b0ad",
    "ATSCL": "62d97d16a6c0a53fd7eddaf0",
    "ROKUPR": "62d97d16a6c0a53fd7eddaf0",
    "SCTCL": "557058:32697a34-9231-4032-9409-b24247903b5c",
}
_HEADINGS = {"Objetivo", "Contexto", "Alcance", "Otra información"}
_STATUS_TAIL = re.compile(
    r"(?:\s+)?(?:QA Validation|Roll Out|Done|Canceled|Cancelled|Cancelado|Cancelada)\s*$",
    re.IGNORECASE,
)
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
    assignee_id: str | None = None
    pdf_path: str | None = None
    pdf_name: str | None = None


@dataclass(frozen=True)
class EpicResult:
    already_existed: bool
    key: str
    summary: str
    activity_type: str
    environment: str


def program_code(platform: str) -> str:
    code = _DEVICE_PROGRAM.get((platform or "").strip())
    if code:
        return code
    raise JiraEpicError(f"El dispositivo {platform or '—'} no tiene programa de QCO.")


def assignee_for(program: str) -> str:
    account = _PROGRAM_ASSIGNEE.get(program)
    if not account:
        raise JiraEpicError(f"El programa {program} no tiene persona asignada.")
    return account


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
            *(
                ["", "Listado de QA/QC Bugs", *_lines(qc_bugs, "")]
                if qc_bugs
                else []
            ),
            "",
            f"Tipo de prueba: {scope}",
            "",
            "Otra información",
            "",
            f"RN: {rn}",
            "",
            f"Ambiente: {environment}",
            "",
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
    program = program_code(release.platform)
    summary = epic_summary(program, version, chosen_type)
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
        assignee_id=assignee_for(program),
        pdf_path=analysis.pdf_file_path if analysis is not None else None,
        pdf_name=analysis.pdf_filename if analysis is not None else None,
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
    content = read_release_note_pdf(draft.pdf_path)
    if content:
        _attach(key, draft.pdf_name or "RN.pdf", content)
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
        rest = _strip_status(rest)
        text = f"- {key} {rest}".strip() if rest else f"- {key}"
        lines.append(text[:240])
    return lines


def _fields(draft: EpicDraft) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "project": {"key": PROJECT_KEY},
        "issuetype": {"name": ISSUE_EPIC},
        "summary": draft.summary,
        "priority": {"id": PRIORITY_ID},
        "description": _adf(draft.description),
        "labels": ["qcpulse", f"qcpulse-r{draft.release_id}"],
    }
    if draft.assignee_id:
        fields["assignee"] = {"accountId": draft.assignee_id}
    account = _account_id()
    if account:
        fields["reporter"] = {"accountId": account}
    return fields


def _strip_status(title: str) -> str:
    text = title
    while True:
        cleaned = _STATUS_TAIL.sub("", text).strip(" :-")
        if cleaned == text:
            return cleaned
        text = cleaned


def _adf(text: str) -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            content.append({"type": "paragraph", "content": []})
            continue
        marks = [{"type": "strong"}] if line.strip() in _HEADINGS else None
        node: dict[str, Any] = {"type": "text", "text": line}
        if marks:
            node["marks"] = marks
        content.append({"type": "paragraph", "content": [node]})
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


def _attach(key: str, filename: str, content: bytes) -> None:
    safe_name = filename.replace("/", "-").replace("\\", "-") or "RN.pdf"
    with _client() as client:
        response = client.post(
            f"/rest/api/3/issue/{key}/attachments",
            headers={"X-Atlassian-Token": "no-check"},
            files={"file": (safe_name, content, "application/pdf")},
        )
    if response.status_code not in (200, 201):
        raise JiraApiError(response.status_code, response.text[:800])


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
