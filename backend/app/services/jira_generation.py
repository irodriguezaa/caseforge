"""Jira issue context for Release Apps case generation.

Uses the documented dual-source fields from Prompt v4. Does not invent tickets or AC.
KPI radar fetching stays in jira_client.fetch_tickets_by_filter.
"""

from __future__ import annotations

from typing import Any

from app.services.jira_client import JiraApiError, JiraNotConfiguredError, _client

# Documented in Prompt v4 — not discovered ad hoc.
_FIELD_USER_STORY_AC = "customfield_19114"
_FIELD_PRODUCT_BRIEF = "customfield_19094"
_FIELD_TBRFRE_DEVICE = "customfield_12104"

_ISSUE_FIELDS = [
    "summary",
    "issuetype",
    "description",
    "parent",
    "status",
    "issuelinks",
    _FIELD_USER_STORY_AC,
    _FIELD_PRODUCT_BRIEF,
    _FIELD_TBRFRE_DEVICE,
]

_GENERATION_TIMEOUT = 30.0


def adf_to_text(value: Any) -> str:
    """Flattens Jira Cloud ADF (or a plain string) to text. No interpretation."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(part for item in value if (part := adf_to_text(item)))
    if not isinstance(value, dict):
        return str(value).strip()
    if value.get("type") == "inlineCard":
        return str((value.get("attrs") or {}).get("url") or "")
    if value.get("type") == "text":
        text = str(value.get("text") or "")
        for mark in value.get("marks") or []:
            if mark.get("type") == "link":
                href = str((mark.get("attrs") or {}).get("href") or "")
                if href and href not in text:
                    return f"{text} {href}".strip()
        return text
    if value.get("type") == "hardBreak":
        return "\n"
    if "content" in value:
        chunks: list[str] = []
        node_type = value.get("type")
        for child in value.get("content") or []:
            chunk = adf_to_text(child)
            if chunk:
                chunks.append(chunk)
        blockish = {
            "doc",
            "paragraph",
            "heading",
            "blockquote",
            "listItem",
            "bulletList",
            "orderedList",
            "table",
            "tableRow",
            "codeBlock",
        }
        if node_type == "tableRow":
            return "| " + " | ".join(chunks) + " |"
        if node_type == "tableCell" or node_type == "tableHeader":
            return " ".join(chunks).strip()
        joined = "\n".join(chunks) if node_type in blockish else " ".join(chunks)
        return joined.strip()
    return ""


def _issue_payload(issue: dict[str, Any]) -> dict[str, Any]:
    fields = issue.get("fields") or {}
    issuetype = fields.get("issuetype") or {}
    parent = fields.get("parent") or {}
    parent_fields = parent.get("fields") or {}
    return {
        "key": issue.get("key"),
        "summary": fields.get("summary") or "",
        "issuetype": (issuetype.get("name") or "").strip(),
        "status": ((fields.get("status") or {}).get("name") or "").strip(),
        "parent_key": parent.get("key"),
        "parent_issuetype": ((parent_fields.get("issuetype") or {}).get("name") or "").strip(),
        "description": adf_to_text(fields.get("description"))[:12000],
        "acceptance_criteria": adf_to_text(fields.get(_FIELD_USER_STORY_AC))[:8000],
        "product_brief_summary": adf_to_text(fields.get(_FIELD_PRODUCT_BRIEF))[:2000],
        "device": adf_to_text(fields.get(_FIELD_TBRFRE_DEVICE)),
    }


def _is_epic(issuetype: str) -> bool:
    return "epic" in issuetype.lower()


def _is_feature_summary(summary: str) -> bool:
    return summary.strip().lower().startswith("feature")


def _get_issue(client, key: str) -> dict[str, Any] | None:
    response = client.get(f"/rest/api/3/issue/{key}", params={"fields": ",".join(_ISSUE_FIELDS)})
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise JiraApiError(response.status_code, response.text[:500])
    return response.json()


def _search_children(client, parent_key: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    next_page_token: str | None = None
    jql = f'parent = "{parent_key}" ORDER BY key ASC'
    while True:
        body: dict[str, Any] = {
            "jql": jql,
            "maxResults": 100,
            "fields": _ISSUE_FIELDS,
        }
        if next_page_token:
            body["nextPageToken"] = next_page_token
        response = client.post("/rest/api/3/search/jql", json=body)
        if response.status_code != 200:
            raise JiraApiError(response.status_code, response.text[:500])
        payload = response.json()
        issues.extend(payload.get("issues") or [])
        next_page_token = payload.get("nextPageToken") or None
        if not next_page_token:
            break
    return issues


def fetch_issuetypes_for_keys(keys: list[str]) -> dict[str, str]:
    """One JQL search for issuetype only. Empty if Jira is missing or a key 404s.

    Used to split RN QA/QC rows into QA Bug vs QC Bug. Does not load epics, children, or Gherkin.
    """
    unique: list[str] = []
    seen: set[str] = set()
    for key in keys:
        normalized = (key or "").strip().upper()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    if not unique:
        return {}
    try:
        client_cm = _client(timeout=_GENERATION_TIMEOUT)
    except JiraNotConfiguredError:
        return {}

    found: dict[str, str] = {}
    try:
        with client_cm as client:
            for start in range(0, len(unique), 50):
                chunk = unique[start : start + 50]
                jql = "key in (" + ", ".join(chunk) + ")"
                next_page_token: str | None = None
                while True:
                    body: dict[str, Any] = {
                        "jql": jql,
                        "maxResults": 100,
                        "fields": ["issuetype"],
                    }
                    if next_page_token:
                        body["nextPageToken"] = next_page_token
                    response = client.post("/rest/api/3/search/jql", json=body)
                    if response.status_code != 200:
                        break
                    payload = response.json()
                    for issue in payload.get("issues") or []:
                        key = str(issue.get("key") or "").strip().upper()
                        fields = issue.get("fields") or {}
                        name = ((fields.get("issuetype") or {}).get("name") or "").strip()
                        if key and name:
                            found[key] = name
                    next_page_token = payload.get("nextPageToken") or None
                    if not next_page_token:
                        break
    except JiraApiError:
        return found
    return found


def fetch_artifacts_for_keys(keys: list[str]) -> list[dict[str, Any]]:
    """Loads RN functionality tickets from Jira. Empty if Jira is not configured or a key 404s.

    Generation continues without Jira rather than failing the Release Apps preview.
    """
    unique = []
    seen: set[str] = set()
    for key in keys:
        normalized = (key or "").strip().upper()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    if not unique:
        return []
    try:
        client_cm = _client(timeout=_GENERATION_TIMEOUT)
    except JiraNotConfiguredError:
        return []

    artifacts: list[dict[str, Any]] = []
    try:
        with client_cm as client:
            for key in unique:
                try:
                    raw = _get_issue(client, key)
                except JiraApiError:
                    continue
                if raw is None:
                    continue
                artifact = _issue_payload(raw)
                children_raw = []
                if _is_epic(artifact["issuetype"]):
                    try:
                        children_raw = _search_children(client, key)
                    except JiraApiError:
                        children_raw = []
                feature_children = [
                    _issue_payload(child)
                    for child in children_raw
                    if _is_feature_summary((child.get("fields") or {}).get("summary") or "")
                ]
                artifact["children"] = feature_children
                artifact["child_count"] = len(children_raw)
                artifact["feature_child_count"] = len(feature_children)
                artifacts.append(artifact)
    except JiraApiError:
        return artifacts
    return artifacts
