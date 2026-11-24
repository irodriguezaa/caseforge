"""Create one QCO Epic per deliverable and one Task per version.

The Epic title is PROGRAMA | VERSIÓN | TIPO. A later version of the same
deliverable renames that Epic with Ciclo1, Ciclo2, … and adds only the new
scope. Each version gets its own Task, assigned to the same person, with the
Epic in Principal. That task gets one Subtask per functionality, one for the
QC bugs, and one whose description is the regression type.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.release import Release
from app.models.release_analysis import ReleaseAnalysis
from app.models.test_case import TestCase
from app.schemas.release import ActivityType, EnvironmentName
from app.services.jira_client import JiraApiError, _client, _require_config
from app.services.rn_storage import read_release_note_pdf

PROJECT_KEY = "QCO"
ISSUE_EPIC = "Epic"
ISSUE_TASK = "Tarea"
ISSUE_SUBTASK = "Subtarea"
# Scrum board "QC Sprint". Its filter is the QCO project.
QC_SPRINT_BOARD_ID = 6999
_SPRINT_PAGE = 50
# The scheme lists this priority as "Importante", but creating with the name is rejected.
# The id is what QCO accepts.
PRIORITY_ID = "3"
# "Fecha de inicio". The timeline draws the version bar from this field plus duedate.
START_DATE_FIELD = "customfield_18528"
# Atlassian Team. The timeline groups the version under QC_{program}.
TEAM_FIELD = "customfield_16200"
_PROGRAM_TEAM = {
    "WEBCL": "3e402041-0ea6-4a16-af8a-c5dc5ca2eecb",
    "AAFCL": "d3c706a6-c2e1-4069-ab6e-ae6676a7d6bf",
    "ADTCL": "659b1000-57eb-47e4-831b-fd572d9f8f7d",
    "WINCL": "56d058f6-062a-400a-b4ea-fca28233386d",
    "STVCL": "6ce1a917-4bdc-4491-b169-c09e0966b849",
    "IOSPR": "ef63ffdd-8eca-411d-ab14-8a28be846621",
    "TVOSPR": "c8fe8ffd-bec0-43e9-981e-3c966cda3aa1",
    "ADRPR": "3445188a-2fbf-453a-8761-5bb9d1243e35",
    "C9085PR": "4cff1b54-e668-4629-9a0b-e58a20e57ebb",
    "ROKUPR": "dd4f0d43-4e3e-4fe8-aed6-39979e989225",
}
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
_KEY_RE = re.compile(r"^([A-Z][A-Z0-9]+)-\d+$")
_ENVIRONMENTS = {"BERC", "FEHF", "OPER", "PROD"}
_RELEASE_LABEL = re.compile(r"^qcpulse-r(\d+)$")


class JiraEpicError(Exception):
    """The release is not ready to open an Epic."""


@dataclass(frozen=True)
class VersionScope:
    release_id: int
    version: str
    device: str
    environment: str
    validation_type: str | None
    rn_filename: str | None
    activity_type: str
    functionalities: tuple[tuple[str, str], ...]
    qc_bugs: tuple[tuple[str, str], ...]


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
    deliverable_id: int | None = None
    program: str = ""
    scopes: tuple[VersionScope, ...] = ()
    start_on: str = ""
    end_on: str = ""


@dataclass(frozen=True)
class SubtaskDraft:
    summary: str
    description: str


@dataclass(frozen=True)
class SprintChoice:
    id: int
    name: str
    state: str
    label: str
    start_at: str = ""
    start_on: str = ""
    end_on: str = ""


@dataclass(frozen=True)
class EpicResult:
    already_existed: bool
    key: str
    summary: str
    activity_type: str
    environment: str
    task_key: str
    task_summary: str
    task_already_existed: bool
    subtask_count: int = 0
    subtasks_already_existed: int = 0
    sprint_id: int | None = None
    sprint_label: str = ""


@dataclass(frozen=True)
class _Plan:
    epic_summary: str
    epic_description: str
    task_summary: str
    task_description: str
    attach_pdf_to_task: bool
    identity_labels: tuple[str, ...]
    task_labels: tuple[str, ...]
    lookup_summaries: tuple[str, ...]
    subtasks: tuple[SubtaskDraft, ...] = ()


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


def team_for(program: str) -> str:
    team_id = _PROGRAM_TEAM.get(program)
    if not team_id:
        raise JiraEpicError(f"El programa {program or '—'} no tiene equipo QC_{program} en Jira.")
    return team_id


def epic_summary(program: str, version: str, activity_type: str) -> str:
    kind = ACTIVITY_TITLE.get(activity_type)
    if kind is None:
        raise JiraEpicError("El tipo debe ser HotFix, Exc, Mantenimiento o Release.")
    version_text = re.sub(r"\s+", " ", (version or "").strip())
    if not version_text:
        raise JiraEpicError("La release no tiene versión.")
    return f"{program} | {version_text} | {kind}"


def cycle_title(program: str, versions: list[str], activity_type: str) -> str:
    if len(versions) == 1:
        return epic_summary(program, versions[0], activity_type)
    kind = ACTIVITY_TITLE.get(activity_type)
    if kind is None:
        raise JiraEpicError("El tipo debe ser HotFix, Exc, Mantenimiento o Release.")
    body = " ".join(f"Ciclo{index}: {version}" for index, version in enumerate(versions, start=1))
    return f"{program} | {body} | {kind}"


def epic_description(
    *,
    device: str,
    version: str,
    environment: str,
    validation_type: str | None,
    rn_filename: str | None,
    functionalities: list[tuple[str, str]],
    qc_bugs: list[tuple[str, str]],
    empty_functionalities: str = "Sin EPC en el RN.",
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
            *_lines(functionalities, empty_functionalities),
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


def accumulated_description(scopes: list[VersionScope]) -> str:
    """Cycle 1 keeps its full text. Each later cycle adds only the new keys."""
    if not scopes:
        raise JiraEpicError("La release no tiene versión.")
    text = _description_for(scopes[0])
    if len(scopes) == 1:
        return text
    seen_func = _keyset(scopes[0].functionalities)
    seen_bugs = _keyset(scopes[0].qc_bugs)
    extra: list[str] = []
    for scope in scopes[1:]:
        new_func = _unseen(scope.functionalities, seen_func)
        new_bugs = _unseen(scope.qc_bugs, seen_bugs)
        seen_func.update(_keyset(scope.functionalities))
        seen_bugs.update(_keyset(scope.qc_bugs))
        extra.extend(_delta_lines(scope, new_func, new_bugs))
    marker = "\nOtra información\n"
    if marker not in text:
        return text.rstrip() + "\n\n" + "\n".join(extra).strip("\n")
    head, tail = text.split(marker, 1)
    return head.rstrip() + "\n\n" + "\n".join(extra).strip("\n") + "\n\nOtra información\n" + tail


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
    if chosen_env not in _ENVIRONMENTS:
        raise JiraEpicError("Elige el Ambiente: BERC, FEHF, OPER o PROD.")

    case_count = db.scalar(
        select(func.count()).select_from(TestCase).where(TestCase.release_id == release.id)
    )
    if not case_count:
        raise JiraEpicError("Genera los casos de prueba antes de crear la EPC.")

    if activity_type is not None:
        release.activity_type = activity_type
    if environment is not None:
        release.environment = environment
    if release.start_date is None or release.end_date is None:
        raise JiraEpicError("Pon el inicio y el fin de la revisión antes de crear los artefactos.")
    program = program_code(release.platform)
    team_for(program)
    scopes = tuple(
        _scope_for_release(db, row, chosen_type, chosen_env) for row in _deliverable_releases(db, release)
    )
    current = next(scope for scope in scopes if scope.release_id == release.id)
    analysis = _latest_analysis(db, release.id)
    summary = cycle_title(program, [current.version], chosen_type)
    description = _description_for(current)
    return EpicDraft(
        release_id=release.id,
        summary=summary,
        description=description,
        activity_type=chosen_type,
        environment=chosen_env,
        assignee_id=assignee_for(program),
        pdf_path=analysis.pdf_file_path if analysis is not None else None,
        pdf_name=analysis.pdf_filename if analysis is not None else None,
        deliverable_id=release.deliverable_id,
        program=program,
        scopes=scopes,
        start_on=release.start_date.isoformat(),
        end_on=release.end_date.isoformat(),
    )


def publish_epic(draft: EpicDraft, sprint_id: int | None = None) -> EpicResult:
    sprint = _require_sprint(sprint_id) if sprint_id is not None else None
    if sprint is not None and (not draft.start_on or not draft.end_on):
        raise JiraEpicError("Pon el inicio y el fin de la revisión antes de crear los artefactos.")
    if sprint is not None and draft.program:
        team_for(draft.program)
    plan = _publication(draft)
    epic_key, epic_existed = _ensure_epic(draft, plan)
    _attach_release_note(epic_key, draft)
    task_key, task_existed = _ensure_task(draft, plan, epic_key)
    if plan.attach_pdf_to_task:
        _attach_release_note(task_key, draft)
    subtasks = _ensure_subtasks(draft, plan, task_key)
    if sprint is not None:
        _move_issues_to_sprint(
            sprint.id,
            [epic_key, task_key, *[key for key, _existed in subtasks]],
        )
        _schedule_version(draft, epic_key, task_key)
    return EpicResult(
        already_existed=epic_existed,
        key=epic_key,
        summary=plan.epic_summary,
        activity_type=draft.activity_type,
        environment=draft.environment,
        task_key=task_key,
        task_summary=plan.task_summary,
        task_already_existed=task_existed,
        subtask_count=len(subtasks),
        subtasks_already_existed=sum(1 for _key, existed in subtasks if existed),
        sprint_id=sprint.id if sprint is not None else None,
        sprint_label=sprint.label if sprint is not None else "",
    )


def list_qc_sprints() -> list[SprintChoice]:
    """Active and future sprints on the QC Sprint board, earliest first."""
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        with _client() as client:
            response = client.get(
                f"/rest/agile/1.0/board/{QC_SPRINT_BOARD_ID}/sprint",
                params={"state": "active,future", "startAt": start, "maxResults": _SPRINT_PAGE},
            )
        if response.status_code != 200:
            raise JiraApiError(response.status_code, response.text[:500])
        body = response.json()
        values = body.get("values") or []
        if isinstance(values, list):
            rows.extend(row for row in values if isinstance(row, dict))
        if body.get("isLast", True) or not values:
            break
        start += len(values)
    choices = [choice for row in rows if (choice := _sprint_choice(row)) is not None]
    choices.sort(key=lambda choice: (choice.start_at, choice.id))
    return choices


def _require_sprint(sprint_id: int) -> SprintChoice:
    match = next((choice for choice in list_qc_sprints() if choice.id == sprint_id), None)
    if match is None:
        raise JiraEpicError("Ese sprint no está en el tablero de QC.")
    return match


def _move_issues_to_sprint(sprint_id: int, keys: list[str]) -> None:
    pending = [key for key in dict.fromkeys(keys) if key]
    for offset in range(0, len(pending), _SPRINT_PAGE):
        _post_sprint_issues(sprint_id, pending[offset : offset + _SPRINT_PAGE])


def _schedule_version(draft: EpicDraft, epic_key: str, task_key: str) -> None:
    """Timeline bar uses the QC Pulse review window. Team is QC_{program}."""
    if not draft.start_on or not draft.end_on:
        return
    fields: dict[str, Any] = {START_DATE_FIELD: draft.start_on, "duedate": draft.end_on}
    if draft.program:
        fields[TEAM_FIELD] = team_for(draft.program)
    for key in dict.fromkeys([epic_key, task_key]):
        if key:
            _put_fields(key, fields)


def _post_sprint_issues(sprint_id: int, keys: list[str]) -> None:
    with _client() as client:
        response = client.post(
            f"/rest/agile/1.0/sprint/{sprint_id}/issue",
            json={"issues": keys},
        )
    if response.status_code not in (200, 204):
        raise JiraApiError(response.status_code, response.text[:800])


_MONTHS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def _sprint_choice(row: dict[str, Any]) -> SprintChoice | None:
    state = str(row.get("state") or "")
    if state not in {"active", "future"}:
        return None
    sprint_id = row.get("id")
    name = str(row.get("name") or "").strip()
    if not isinstance(sprint_id, int) or not name:
        return None
    start = _sprint_day(row.get("startDate"))
    end = _sprint_day(row.get("endDate"))
    label = f"{name} · {start} – {end}" if start and end else name
    return SprintChoice(
        id=sprint_id,
        name=name,
        state=state,
        label=label,
        start_at=str(row.get("startDate") or ""),
        start_on=_sprint_iso_day(row.get("startDate")),
        end_on=_sprint_iso_day(row.get("endDate")),
    )


def _sprint_day(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(ZoneInfo("America/Mexico_City"))
    except ValueError:
        return ""
    return f"{moment.day} {_MONTHS[moment.month - 1]}"


def _sprint_iso_day(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(ZoneInfo("America/Mexico_City"))
    except ValueError:
        return ""
    return moment.date().isoformat()


def _description_for(scope: VersionScope) -> str:
    return epic_description(
        device=scope.device,
        version=scope.version,
        environment=scope.environment,
        validation_type=scope.validation_type,
        rn_filename=scope.rn_filename,
        functionalities=list(scope.functionalities),
        qc_bugs=list(scope.qc_bugs),
    )


def task_description(scopes: list[VersionScope], current: VersionScope) -> str:
    """The first version lists its whole RN. A later version lists only new keys."""
    if not any(scope.release_id < current.release_id for scope in scopes):
        return _description_for(current)
    functionalities, bugs = _scoped_items(scopes, current)
    return epic_description(
        device=current.device,
        version=current.version,
        environment=current.environment,
        validation_type=current.validation_type,
        rn_filename=current.rn_filename,
        functionalities=functionalities,
        qc_bugs=bugs,
        empty_functionalities="No hay nuevas funcionalidades",
    )


def subtasks_for(program: str, scopes: list[VersionScope], current: VersionScope) -> tuple[SubtaskDraft, ...]:
    """One subtask per functionality, one for the QC bugs, and one for the regression type."""
    functionalities, bugs = _scoped_items(scopes, current)
    version = current.version
    rows: list[SubtaskDraft] = []
    seen: set[str] = set()
    for key, _title in functionalities:
        token = str(key).strip().upper()
        if token in seen or not _KEY_RE.match(token):
            continue
        seen.add(token)
        rows.append(
            SubtaskDraft(
                summary=f"{program} | {version} | {token}",
                description=f"Validación funcional de {token} con la versión {version}",
            )
        )
    if bugs:
        listing = "\n".join(
            [
                f"Validación de los siguientes QC Bugs con la versión {version}:",
                "",
                *_lines(bugs, ""),
            ]
        ).strip()
        rows.append(SubtaskDraft(summary=f"{program} | {version} | Revisión QC Bugs", description=listing))
    regression = (current.validation_type or "").strip() or "Sin tipo de prueba"
    rows.append(SubtaskDraft(summary=f"{program} | {version} | REGRESIÓN", description=regression))
    return tuple(rows)


def _delta_lines(
    scope: VersionScope,
    functionalities: list[tuple[str, str]],
    bugs: list[tuple[str, str]],
) -> list[str]:
    lines = [f"Nuevo alcance en la versión {scope.version}", ""]
    if functionalities:
        lines.extend(["Listado de EPCs (funcionalidades)", *_lines(functionalities, ""), ""])
    if bugs:
        lines.extend(["Listado de QA/QC Bugs", *_lines(bugs, ""), ""])
    regression = (scope.validation_type or "").strip() or "Sin tipo de prueba"
    lines.append(f"Tipo de regresión: {regression}")
    return lines


def _keyset(items: tuple[tuple[str, str], ...] | list[tuple[str, str]]) -> set[str]:
    return {key.strip().upper() for key, _title in items if _KEY_RE.match(str(key).strip().upper())}


def _unseen(items: tuple[tuple[str, str], ...], seen: set[str]) -> list[tuple[str, str]]:
    fresh: list[tuple[str, str]] = []
    for key, title in items:
        token = str(key).strip().upper()
        if _KEY_RE.match(token) and token not in seen:
            fresh.append((token, title))
    return fresh


def _scoped_items(
    scopes: list[VersionScope],
    current: VersionScope,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    seen_func: set[str] = set()
    seen_bugs: set[str] = set()
    for scope in scopes:
        if scope.release_id >= current.release_id:
            continue
        seen_func.update(_keyset(scope.functionalities))
        seen_bugs.update(_keyset(scope.qc_bugs))
    return _unseen(current.functionalities, seen_func), _unseen(current.qc_bugs, seen_bugs)


def _deliverable_releases(db: Session, release: Release) -> list[Release]:
    if release.deliverable_id is None:
        return [release]
    rows = list(
        db.scalars(
            select(Release)
            .where(Release.deliverable_id == release.deliverable_id)
            .order_by(Release.id.asc())
        ).all()
    )
    if not any(row.id == release.id for row in rows):
        rows.append(release)
        rows.sort(key=lambda row: row.id)
    return rows or [release]


def _latest_analysis(db: Session, release_id: int) -> ReleaseAnalysis | None:
    return db.scalars(
        select(ReleaseAnalysis)
        .where(ReleaseAnalysis.release_id == release_id)
        .order_by(ReleaseAnalysis.created_at.desc())
    ).first()


def _scope_for_release(
    db: Session,
    release: Release,
    fallback_type: str,
    fallback_env: str,
) -> VersionScope:
    version = re.sub(r"\s+", " ", (release.version or "").strip())
    if not version:
        raise JiraEpicError("La release no tiene versión.")
    kind = release.activity_type if release.activity_type in ACTIVITY_TITLE else fallback_type
    environment = release.environment if release.environment in _ENVIRONMENTS else fallback_env
    analysis = _latest_analysis(db, release.id)
    functionalities = _bucket(analysis, "technical_epics")
    bugs = _bucket(analysis, "qc_bugs") or _bucket(analysis, "qa_qc")
    keys = [key for key, _title in functionalities]
    if not keys:
        keys = _case_keys(db, release.id)
        functionalities = [(key, "") for key in keys]
    return VersionScope(
        release_id=release.id,
        version=version,
        device=release.platform,
        environment=environment,
        validation_type=release.validation_type,
        rn_filename=analysis.pdf_filename if analysis is not None else None,
        activity_type=kind,
        functionalities=tuple(functionalities),
        qc_bugs=tuple(bugs),
    )


def _identity_labels(deliverable_id: int | None, release_ids: tuple[int, ...]) -> tuple[str, ...]:
    labels: list[str] = []
    if deliverable_id is not None:
        labels.append(f"qcpulse-d{deliverable_id}")
    for release_id in release_ids:
        label = f"qcpulse-r{release_id}"
        if label not in labels:
            labels.append(label)
    return tuple(labels)


def _publication(draft: EpicDraft) -> _Plan:
    if not draft.scopes:
        labels = _identity_labels(draft.deliverable_id, (draft.release_id,))
        return _Plan(
            epic_summary=draft.summary,
            epic_description=draft.description,
            task_summary=draft.summary,
            task_description=draft.description,
            attach_pdf_to_task=False,
            identity_labels=labels,
            task_labels=labels,
            lookup_summaries=(draft.summary,),
        )
    if not draft.program:
        raise JiraEpicError("El dispositivo no tiene programa de QCO.")
    published = _published_release_ids([scope.release_id for scope in draft.scopes])
    latest = max([draft.release_id, *published])
    included = [scope for scope in draft.scopes if scope.release_id <= latest]
    current = next((scope for scope in draft.scopes if scope.release_id == draft.release_id), None)
    if current is None or not included:
        raise JiraEpicError("La release no tiene versión.")
    kind = included[0].activity_type if included[0].activity_type in ACTIVITY_TITLE else draft.activity_type
    versions = [scope.version for scope in included]
    epic_summary = cycle_title(draft.program, versions, kind)
    single_titles = tuple(cycle_title(draft.program, [scope.version], kind) for scope in included)
    return _Plan(
        epic_summary=epic_summary,
        epic_description=accumulated_description(included),
        task_summary=cycle_title(draft.program, [current.version], draft.activity_type),
        task_description=task_description(included, current),
        attach_pdf_to_task=included[0].release_id != current.release_id,
        identity_labels=_identity_labels(draft.deliverable_id, tuple(scope.release_id for scope in included)),
        task_labels=_identity_labels(draft.deliverable_id, (current.release_id,)),
        lookup_summaries=tuple(dict.fromkeys((epic_summary, *single_titles))),
        subtasks=subtasks_for(draft.program, included, current),
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
    for key, _title in items:
        token = str(key or "").strip().upper()
        if _KEY_RE.match(token):
            lines.append(f"- {token}")
    return lines or [empty]


def _stored_labels(identity: tuple[str, ...]) -> list[str]:
    labels = ["qcpulse"]
    for label in identity:
        if label not in labels:
            labels.append(label)
    return labels


def _issue_fields(
    *,
    issuetype: str,
    summary: str,
    description: str,
    labels: list[str],
    assignee_id: str | None,
    parent_key: str | None = None,
) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "project": {"key": PROJECT_KEY},
        "issuetype": {"name": issuetype},
        "summary": summary,
        "priority": {"id": PRIORITY_ID},
        "description": _adf(description),
        "labels": labels,
    }
    if assignee_id:
        fields["assignee"] = {"accountId": assignee_id}
    if parent_key:
        fields["parent"] = {"key": parent_key}
    account = _account_id()
    if account:
        fields["reporter"] = {"accountId": account}
    return fields


_ISSUE_LINE = re.compile(r"^- ([A-Z][A-Z0-9]+-\d+)$")


def _issue_url(key: str) -> str:
    base = (settings.jira_base_url or "https://dlatvarg.atlassian.net").rstrip("/")
    return f"{base}/browse/{key}"


def _adf(text: str) -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []

    def flush_issues() -> None:
        if not issues:
            return
        content.append({"type": "bulletList", "content": list(issues)})
        issues.clear()

    for line in text.splitlines():
        match = _ISSUE_LINE.match(line.strip())
        if match:
            issues.append(
                {
                    "type": "listItem",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {"type": "inlineCard", "attrs": {"url": _issue_url(match.group(1))}}
                            ],
                        }
                    ],
                }
            )
            continue
        flush_issues()
        if not line.strip():
            content.append({"type": "paragraph", "content": []})
            continue
        node: dict[str, Any] = {"type": "text", "text": line}
        stripped = line.strip()
        if stripped in _HEADINGS or stripped.startswith("Nuevo alcance en la versión"):
            node["marks"] = [{"type": "strong"}]
        content.append({"type": "paragraph", "content": [node]})
    flush_issues()
    if not content:
        content = [{"type": "paragraph", "content": [{"type": "text", "text": "QC Pulse"}]}]
    return {"type": "doc", "version": 1, "content": content}


def _put_fields(key: str, fields: dict[str, Any]) -> None:
    with _client() as client:
        response = client.put(f"/rest/api/3/issue/{key}", json={"fields": fields})
    if response.status_code not in (200, 204):
        raise JiraApiError(response.status_code, response.text[:800])


def _jql_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _ensure_epic(draft: EpicDraft, plan: _Plan) -> tuple[str, bool]:
    existing = _find_epic(plan.identity_labels, plan.lookup_summaries)
    if existing:
        _put_fields(
            existing,
            {
                "summary": plan.epic_summary,
                "description": _adf(plan.epic_description),
                "labels": _merge_labels(existing, plan.identity_labels),
            },
        )
        return existing, True
    key = _create_issue(
        _issue_fields(
            issuetype=ISSUE_EPIC,
            summary=plan.epic_summary,
            description=plan.epic_description,
            labels=_stored_labels(plan.identity_labels),
            assignee_id=draft.assignee_id,
        )
    )
    return key, False


def _ensure_task(draft: EpicDraft, plan: _Plan, epic_key: str) -> tuple[str, bool]:
    existing = _find_by_summary(ISSUE_TASK, plan.task_summary)
    if existing:
        fields: dict[str, Any] = {
            "description": _adf(plan.task_description),
            "parent": {"key": epic_key},
        }
        if draft.assignee_id:
            fields["assignee"] = {"accountId": draft.assignee_id}
        _put_fields(existing, fields)
        return existing, True
    key = _create_issue(
        _issue_fields(
            issuetype=ISSUE_TASK,
            summary=plan.task_summary,
            description=plan.task_description,
            labels=_stored_labels(plan.task_labels),
            assignee_id=draft.assignee_id,
            parent_key=epic_key,
        )
    )
    return key, False


def _ensure_subtasks(draft: EpicDraft, plan: _Plan, task_key: str) -> list[tuple[str, bool]]:
    ensured: list[tuple[str, bool]] = []
    for subtask in plan.subtasks:
        existing = _find_subtask(task_key, subtask.summary)
        if existing:
            fields: dict[str, Any] = {
                "description": _adf(subtask.description),
                "parent": {"key": task_key},
            }
            if draft.assignee_id:
                fields["assignee"] = {"accountId": draft.assignee_id}
            _put_fields(existing, fields)
            ensured.append((existing, True))
            continue
        key = _create_issue(
            _issue_fields(
                issuetype=ISSUE_SUBTASK,
                summary=subtask.summary,
                description=subtask.description,
                labels=_stored_labels(plan.task_labels),
                assignee_id=draft.assignee_id,
                parent_key=task_key,
            )
        )
        ensured.append((key, False))
    return ensured


def _find_subtask(parent_key: str, summary: str) -> str | None:
    jql = (
        f"project = {PROJECT_KEY} AND issuetype = {_jql_quote(ISSUE_SUBTASK)} "
        f"AND parent = {parent_key} AND summary = {_jql_quote(summary)} ORDER BY created DESC"
    )
    issues = _search(jql, limit=1)
    return str(issues[0]["key"]) if issues else None


def _find_epic(labels: tuple[str, ...], summaries: tuple[str, ...]) -> str | None:
    if labels:
        quoted = ", ".join(_jql_quote(label) for label in labels)
        jql = (
            f"project = {PROJECT_KEY} AND issuetype = {_jql_quote(ISSUE_EPIC)} "
            f"AND labels in ({quoted}) ORDER BY created ASC"
        )
        issues = _search(jql, limit=5)
        if issues:
            return str(issues[0]["key"])
    for summary in summaries:
        found = _find_by_summary(ISSUE_EPIC, summary)
        if found:
            return found
    return None


def _find_by_summary(issuetype: str, summary: str) -> str | None:
    jql = (
        f"project = {PROJECT_KEY} AND issuetype = {_jql_quote(issuetype)} "
        f"AND summary = {_jql_quote(summary)} ORDER BY created DESC"
    )
    issues = _search(jql, limit=1)
    return str(issues[0]["key"]) if issues else None


def _published_release_ids(release_ids: list[int]) -> set[int]:
    if not release_ids:
        return set()
    quoted = ", ".join(_jql_quote(f"qcpulse-r{release_id}") for release_id in release_ids)
    jql = (
        f"project = {PROJECT_KEY} AND issuetype = {_jql_quote(ISSUE_TASK)} "
        f"AND labels in ({quoted}) ORDER BY created ASC"
    )
    found: set[int] = set()
    for issue in _search(jql, limit=50, fields=["labels"]):
        labels = (issue.get("fields") or {}).get("labels") or []
        for label in labels:
            match = _RELEASE_LABEL.match(str(label))
            if match:
                found.add(int(match.group(1)))
    return found


def _merge_labels(key: str, identity: tuple[str, ...]) -> list[str]:
    merged = _read_labels(key)
    for label in _stored_labels(identity):
        if label not in merged:
            merged.append(label)
    return merged


def _read_labels(key: str) -> list[str]:
    with _client() as client:
        response = client.get(f"/rest/api/3/issue/{key}", params={"fields": "labels"})
    if response.status_code != 200:
        return []
    labels = ((response.json().get("fields") or {}).get("labels") or [])
    return [str(label) for label in labels]


def _search(
    jql: str,
    limit: int = 5,
    fields: list[str] | None = None,
) -> list[dict[str, Any]]:
    with _client() as client:
        response = client.post(
            "/rest/api/3/search/jql",
            json={"jql": jql, "maxResults": limit, "fields": fields or ["summary"]},
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
        raise JiraApiError(response.status_code, "Jira no devolvió la clave del artefacto.")
    return key


def _attachment_name(filename: str | None) -> str:
    return (filename or "RN.pdf").replace("/", "-").replace("\\", "-") or "RN.pdf"


def _attach_release_note(key: str, draft: EpicDraft) -> None:
    content = read_release_note_pdf(draft.pdf_path)
    if not content:
        return
    name = _attachment_name(draft.pdf_name)
    if _has_attachment(key, name):
        return
    _attach(key, name, content)


def _has_attachment(key: str, filename: str) -> bool:
    with _client() as client:
        response = client.get(f"/rest/api/3/issue/{key}", params={"fields": "attachment"})
    if response.status_code != 200:
        return False
    rows = ((response.json().get("fields") or {}).get("attachment") or [])
    return any(str((row or {}).get("filename") or "") == filename for row in rows)


def _attachment_client() -> httpx.Client:
    # The shared client forces application/json. Jira rejects that on /attachments.
    base_url, email, token = _require_config()
    return httpx.Client(
        base_url=base_url,
        auth=(email, token),
        timeout=120,
        headers={"Accept": "application/json", "X-Atlassian-Token": "no-check"},
    )


def _attach(key: str, filename: str, content: bytes) -> None:
    with _attachment_client() as client:
        response = client.post(
            f"/rest/api/3/issue/{key}/attachments",
            files={"file": (filename, content, "application/pdf")},
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
