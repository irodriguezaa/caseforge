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

from datetime import date, datetime
from typing import Any

import httpx

from app.config import settings
from app.models.qc_ticket import QcTicketPriority, QcTicketSource, QcTicketView
from app.schemas.qc_tickets import QcTicketCreate
from app.services.cluster_resolution import resolve_cluster

_REQUEST_TIMEOUT_SECONDS = 15.0
_CLOSED_STATUS_CATEGORIES = {"done"}  # Jira's own statusCategory.key for "closed-like" statuses


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


def _client() -> httpx.Client:
    base_url, email, token = _require_config()
    return httpx.Client(
        base_url=base_url,
        auth=(email, token),
        timeout=_REQUEST_TIMEOUT_SECONDS,
        headers={"Accept": "application/json"},
    )


def list_fields() -> list[dict[str, str]]:
    """Returns [{id, name}] for every field in the Jira instance -- use this to find which
    customfield_XXXXX corresponds to 'Cluster' without guessing."""
    with _client() as client:
        response = client.get("/rest/api/3/field")
    if response.status_code != 200:
        raise JiraApiError(response.status_code, response.text[:500])
    return [{"id": f["id"], "name": f["name"]} for f in response.json()]


def _resolve_priority(raw: str | None) -> QcTicketPriority:
    if not raw:
        return QcTicketPriority.OTHER
    lowered = raw.lower()
    if "impedimento" in lowered or "blocker" in lowered:
        return QcTicketPriority.BLOCKER
    if "crítica" in lowered or "critica" in lowered or "critical" in lowered:
        return QcTicketPriority.CRITICAL
    return QcTicketPriority.OTHER


def _parse_jira_timestamp(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        # Jira Cloud timestamps look like "2026-08-25T15:45:00.000-0600"
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _map_issue(
    issue: dict[str, Any], cluster_field_id: str | None, view: QcTicketView, source: QcTicketSource
) -> QcTicketCreate:
    fields = issue.get("fields", {})
    priority = fields.get("priority") or {}
    status = fields.get("status") or {}
    status_category = (status.get("statusCategory") or {}).get("key", "")
    project = fields.get("project") or {}
    issue_type = fields.get("issuetype") or {}

    cluster_raw = fields.get(cluster_field_id) if cluster_field_id else None
    if isinstance(cluster_raw, dict):
        cluster_raw = cluster_raw.get("value") or cluster_raw.get("name")
    cluster, _cluster_warning = resolve_cluster(cluster_raw, fields.get("summary"))

    created = _parse_jira_timestamp(fields.get("created"))
    if created is None:
        # Jira always sets "created"; if this ever fails, surfacing today's date would silently
        # mislabel the ticket's timeline, so this issue is skipped by the caller instead.
        raise ValueError(f"No se pudo parsear la fecha de creación de {issue.get('key')}")

    return QcTicketCreate(
        issue_key=issue["key"],
        issue_type=issue_type.get("name"),
        project_key=project.get("key"),
        priority_bucket=_resolve_priority(priority.get("name")),
        status_raw=status.get("name", ""),
        is_open=status_category not in _CLOSED_STATUS_CATEGORIES,
        view=view,
        source=source,
        cluster=cluster,
        affected_program=None,
        device=None,
        swf=None,
        created_date=created,
        resolved_date=_parse_jira_timestamp(fields.get("resolutiondate")),
        summary=fields.get("summary"),
    )


def fetch_tickets_by_filter(
    filter_id: str, view: QcTicketView, source: QcTicketSource, cluster_field_id: str | None
) -> tuple[list[QcTicketCreate], list[str]]:
    """Returns (mapped tickets, skipped-issue-keys with unparseable dates)."""
    tickets: list[QcTicketCreate] = []
    skipped: list[str] = []

    with _client() as client:
        start_at = 0
        page_size = 100
        while True:
            response = client.get(
                "/rest/api/3/search",
                params={
                    "jql": f"filter={filter_id}",
                    "startAt": start_at,
                    "maxResults": page_size,
                    "fields": "*all",
                },
            )
            if response.status_code != 200:
                raise JiraApiError(response.status_code, response.text[:500])

            payload = response.json()
            for issue in payload.get("issues", []):
                try:
                    tickets.append(_map_issue(issue, cluster_field_id, view, source))
                except ValueError:
                    skipped.append(issue.get("key", "?"))

            start_at += page_size
            if start_at >= payload.get("total", 0):
                break

    return tickets, skipped
