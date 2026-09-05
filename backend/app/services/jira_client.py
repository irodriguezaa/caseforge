"""Jira Cloud API client for the QcTicket sync feature.

IMPORTANT: this module has NOT been validated against a real Jira instance -- this sandbox has
no network access to atlassian.net. It was written directly against Jira Cloud's documented
REST API v3 (Basic Auth via email + API token, standard for Jira Cloud), but you are the first
one who can actually run it end to end. Report back the exact error if something doesn't work;
the field-discovery endpoint below is the safest starting point since it requires no guessing.

Auth: HTTP Basic with (email, api_token) -- this is the documented method for Jira Cloud.
Server/Data Center instances use a different auth scheme (personal access token as a Bearer
header) and would need a small change here if that's what dlatvarg.atlassian.net turns out to
need (the .atlassian.net domain strongly suggests Cloud, so Basic Auth should be correct).
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import httpx

from app.config import settings
from app.models.qc_ticket import QcTicketSource, QcTicketView
from app.schemas.qc_tickets import QcTicketCreate
from app.services.cluster_resolution import resolve_cluster
from app.services.qc_ticket_imports import (
    _CLOSED_STATUSES_OPERATIVAS,
    _CLOSED_STATUSES_RELEASE,
    _resolve_operativas_device_swf,
    _resolve_priority,
    _resolve_release_swf,
)

_REQUEST_TIMEOUT_SECONDS = 120.0
_SEARCH_PAGE_SIZE = 100
_JIRA_OFFSET_RE = re.compile(r"([+-])(\d{2})(\d{2})$")

# The four saved Jira filters behind KPIs Defectos Operativa / Defectos Release.
RADAR_FILTERS: dict[QcTicketView, tuple[tuple[QcTicketSource, str], ...]] = {
    QcTicketView.OPERATIVAS: (
        (QcTicketSource.QC_DETECTED, "112929"),
        (QcTicketSource.LEAKED, "113062"),
    ),
    QcTicketView.RELEASE: (
        (QcTicketSource.QC_DETECTED, "113261"),
        (QcTicketSource.LEAKED, "113784"),
    ),
}


class JiraNotConfiguredError(Exception):
    """Raised when JIRA_BASE_URL/EMAIL/API_TOKEN aren't set."""


class JiraApiError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"Jira API error {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


def _require_config() -> tuple[str, str, str]:
    if not (settings.jira_base_url and settings.jira_email and settings.jira_api_token):
        raise JiraNotConfiguredError(
            "JIRA_BASE_URL, JIRA_EMAIL y JIRA_API_TOKEN deben estar configurados (ver .env)."
        )
    return settings.jira_base_url.rstrip("/"), settings.jira_email, settings.jira_api_token


def _client(timeout: float | None = None) -> httpx.Client:
    base_url, email, token = _require_config()
    return httpx.Client(
        base_url=base_url,
        auth=(email, token),
        timeout=timeout if timeout is not None else _REQUEST_TIMEOUT_SECONDS,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )


def ensure_authenticated() -> None:
    """Saved filters can be readable without a session; issue search is not.

    A rejected token still gets HTTP 200 + 0 issues from /search/jql, which used to look like
    a successful refresh and leave (or wipe) KPI totals that do not match Jira.
    """
    with _client() as client:
        response = client.get("/rest/api/3/myself")
        if response.status_code != 200:
            raise JiraApiError(
                response.status_code,
                "Jira rechazó JIRA_EMAIL / JIRA_API_TOKEN. El KPI no se puede igualar al filtro "
                "hasta que la cuenta autentique (GET /rest/api/3/myself = 200) y tenga permiso "
                "de lectura de issues.",
            )


def list_fields() -> list[dict[str, str]]:
    """Returns [{id, name}] for every field in the Jira instance -- use this to find which
    customfield_XXXXX corresponds to 'Cluster' without guessing."""
    with _client() as client:
        response = client.get("/rest/api/3/field")
    if response.status_code != 200:
        raise JiraApiError(response.status_code, response.text[:500])
    return [{"id": f["id"], "name": f["name"]} for f in response.json()]


def discover_custom_field_ids() -> tuple[str | None, str | None]:
    """Returns (cluster_field_id, programa_afectado_field_id) by matching Jira field names.

    Avoids the numeric 'Contador Programa Afectado' decoy, same rule as the CSV importer.
    """
    cluster_id: str | None = None
    program_id: str | None = None
    for item in list_fields():
        name = item["name"].strip().lower()
        if name in {"cluster", "campo personalizado (cluster)"}:
            cluster_id = item["id"]
        if name in {"programa afectado", "campo personalizado (programa afectado)"}:
            program_id = item["id"]
    return cluster_id, program_id


def _parse_jira_timestamp(raw: str | None) -> date | None:
    if not raw:
        return None
    text = raw.strip().replace("Z", "+00:00")
    match = _JIRA_OFFSET_RE.search(text)
    if match:
        text = text[: match.start()] + f"{match.group(1)}{match.group(2)}:{match.group(3)}"
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return datetime.strptime(text[:19], "%Y-%m-%dT%H:%M:%S").date()
        except ValueError:
            return None


def _custom_field_text(raw: Any) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        value = raw.get("value") or raw.get("name") or raw.get("displayName")
        return str(value).strip() if value else None
    if isinstance(raw, list) and raw:
        return _custom_field_text(raw[0])
    text = str(raw).strip()
    return text or None


def _linked_issue_keys(issue: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for link in issue.get("fields", {}).get("issuelinks") or []:
        for side in ("outwardIssue", "inwardIssue"):
            other = link.get(side) or {}
            key = other.get("key")
            if key:
                keys.append(key)
    return keys


def _map_issue(
    issue: dict[str, Any],
    cluster_field_id: str | None,
    program_field_id: str | None,
    view: QcTicketView,
    source: QcTicketSource,
) -> QcTicketCreate | None:
    """Maps a Jira issue. Every issue the filter returns is persisted so KPI totals match Jira."""
    fields = issue.get("fields", {})
    priority = fields.get("priority") or {}
    status = fields.get("status") or {}
    project = fields.get("project") or {}
    issue_type = fields.get("issuetype") or {}
    status_raw = status.get("name") or ""
    is_cancelled = "cancel" in status_raw.strip().lower()

    created = _parse_jira_timestamp(fields.get("created"))
    if created is None:
        # Jira always sets "created"; if this ever fails, surfacing today's date would silently
        # mislabel the ticket's timeline, so this issue is skipped by the caller instead.
        raise ValueError(f"No se pudo parsear la fecha de creación de {issue.get('key')}")

    cluster = None
    if view == QcTicketView.OPERATIVAS:
        cluster_raw = _custom_field_text(fields.get(cluster_field_id) if cluster_field_id else None)
        cluster, _cluster_warning = resolve_cluster(cluster_raw, fields.get("summary"))

    affected_program = _custom_field_text(fields.get(program_field_id) if program_field_id else None)
    project_key = project.get("key")
    device = swf = None
    if view == QcTicketView.OPERATIVAS:
        device, swf = _resolve_operativas_device_swf(affected_program, created)
    else:
        device, swf = _resolve_release_swf(project_key)
        if swf == "EXCLUIR":
            swf = "OTROS"

    closed_set = _CLOSED_STATUSES_OPERATIVAS if view == QcTicketView.OPERATIVAS else _CLOSED_STATUSES_RELEASE
    is_open = (not is_cancelled) and status_raw.strip().upper() not in closed_set

    return QcTicketCreate(
        issue_key=issue["key"],
        issue_type=issue_type.get("name"),
        project_key=project_key,
        priority_bucket=_resolve_priority(priority.get("name") or ""),
        status_raw=status_raw,
        is_open=is_open,
        view=view,
        source=source,
        cluster=cluster,
        affected_program=affected_program if view == QcTicketView.OPERATIVAS else None,
        device=device,
        swf=swf,
        created_date=created,
        resolved_date=_parse_jira_timestamp(fields.get("resolutiondate")),
        summary=fields.get("summary"),
    )


@dataclass
class JiraFetchResult:
    tickets: list[QcTicketCreate]
    skipped_invalid: list[str]
    skipped_excluded: int = 0
    raw_issue_count: int = 0
    linked_keys_by_issue: dict[str, list[str]] = field(default_factory=dict)


def _search_fields(cluster_field_id: str | None, program_field_id: str | None) -> list[str]:
    fields = [
        "summary",
        "status",
        "priority",
        "created",
        "resolutiondate",
        "project",
        "issuetype",
        "issuelinks",
    ]
    if cluster_field_id:
        fields.append(cluster_field_id)
    if program_field_id:
        fields.append(program_field_id)
    return fields


def _jql_for_saved_filter(client: httpx.Client, filter_id: str) -> str:
    """Resolves the saved filter to raw JQL. `filter=ID` on /search/jql can match nothing."""
    response = client.get(f"/rest/api/3/filter/{filter_id}")
    if response.status_code != 200:
        raise JiraApiError(response.status_code, response.text[:500])
    jql = (response.json() or {}).get("jql")
    if not jql or not str(jql).strip():
        raise JiraApiError(502, f"El filtro {filter_id} no devolvió JQL.")
    return str(jql)


def fetch_tickets_by_filter(
    filter_id: str,
    view: QcTicketView,
    source: QcTicketSource,
    cluster_field_id: str | None = None,
    program_field_id: str | None = None,
) -> JiraFetchResult:
    """Fetches one saved Jira filter and maps issues with the same rules as the CSV importer."""
    result = JiraFetchResult(tickets=[], skipped_invalid=[])
    field_list = _search_fields(cluster_field_id, program_field_id)

    with _client() as client:
        jql = _jql_for_saved_filter(client, filter_id)
        next_page_token: str | None = None
        while True:
            # CHANGE-2046: /rest/api/3/search was removed. Pagination is nextPageToken, not startAt.
            body: dict[str, Any] = {
                "jql": jql,
                "maxResults": _SEARCH_PAGE_SIZE,
                "fields": field_list,
            }
            if next_page_token:
                body["nextPageToken"] = next_page_token
            response = client.post("/rest/api/3/search/jql", json=body)
            if response.status_code != 200:
                raise JiraApiError(response.status_code, response.text[:500])

            payload = response.json()
            issues = payload.get("issues") or []
            result.raw_issue_count += len(issues)
            for issue in issues:
                try:
                    ticket = _map_issue(issue, cluster_field_id, program_field_id, view, source)
                except ValueError:
                    result.skipped_invalid.append(issue.get("key", "?"))
                    continue
                if ticket is None:
                    result.skipped_excluded += 1
                    continue
                result.tickets.append(ticket)
                links = _linked_issue_keys(issue)
                if links:
                    result.linked_keys_by_issue[ticket.issue_key] = links

            next_page_token = payload.get("nextPageToken") or None
            if not next_page_token or not issues:
                break

    return result
