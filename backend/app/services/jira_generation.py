"""Jira issue context for Release Apps case generation.

Uses the documented dual-source fields from Prompt v4. Does not invent tickets or AC.
KPI radar fetching stays in jira_client.fetch_tickets_by_filter.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.services.jira_client import JiraApiError, JiraNotConfiguredError, _client

# Documented in Prompt v4 — not discovered ad hoc.
_FIELD_USER_STORY_AC = "customfield_19114"
_FIELD_YO_COMO = "customfield_19120"
_FIELD_QUIERO = "customfield_19121"
_FIELD_PARA = "customfield_19122"
_FIELD_TIPO_USUARIO = "customfield_19125"
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
    _FIELD_YO_COMO,
    _FIELD_QUIERO,
    _FIELD_PARA,
    _FIELD_TIPO_USUARIO,
    _FIELD_PRODUCT_BRIEF,
    _FIELD_TBRFRE_DEVICE,
]

_GENERATION_TIMEOUT = 30.0


def field_text(value: Any) -> str:
    """ADF, plain text, or a Jira select/list value. No interpretation."""
    if isinstance(value, dict) and "value" in value and "content" not in value and value.get("type") not in {"doc", "paragraph"}:
        return str(value.get("value") or "").strip()
    if isinstance(value, list) and value and all(isinstance(item, dict) and "value" in item for item in value):
        return ", ".join(str(item.get("value") or "").strip() for item in value if str(item.get("value") or "").strip())
    return adf_to_text(value, number_ordered=True)


def adf_to_text(value: Any, *, number_ordered: bool = False, _list_depth: int = 0) -> str:
    """Flattens Jira Cloud ADF (or a plain string) to text. No interpretation."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(
            part for item in value if (part := adf_to_text(item, number_ordered=number_ordered, _list_depth=_list_depth))
        )
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
        if node_type == "orderedList" and number_ordered:
            lines: list[str] = []
            for index, child in enumerate(value.get("content") or [], start=1):
                body = adf_to_text(child, number_ordered=True, _list_depth=_list_depth + 1).strip()
                if not body:
                    continue
                if _list_depth == 0:
                    lines.append(f"{index}. {body}")
                elif body.startswith("- "):
                    lines.append(body)
                else:
                    lines.append(f"- {body}")
            return "\n".join(lines)
        for child in value.get("content") or []:
            chunk = adf_to_text(child, number_ordered=number_ordered, _list_depth=_list_depth)
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
        "description": adf_to_text(fields.get("description")),
        "acceptance_criteria": field_text(fields.get(_FIELD_USER_STORY_AC)),
        "yo_como": field_text(fields.get(_FIELD_YO_COMO)),
        "quiero": field_text(fields.get(_FIELD_QUIERO)),
        "para": field_text(fields.get(_FIELD_PARA)),
        "user_type": field_text(fields.get(_FIELD_TIPO_USUARIO)),
        "success_criteria": field_text(fields.get(_FIELD_PRODUCT_BRIEF)),
        "product_brief_summary": field_text(fields.get(_FIELD_PRODUCT_BRIEF))[:2000],
        "device": adf_to_text(fields.get(_FIELD_TBRFRE_DEVICE)),
        "linked_issues": _linked_issues(fields),
    }


def _linked_issues(fields: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for link in fields.get("issuelinks") or []:
        if not isinstance(link, dict):
            continue
        for side in ("outwardIssue", "inwardIssue"):
            other = link.get(side) or {}
            key = str(other.get("key") or "").strip()
            if not key:
                continue
            other_fields = other.get("fields") or {}
            rows.append(
                {
                    "key": key,
                    "summary": str(other_fields.get("summary") or ""),
                    "issuetype": str((other_fields.get("issuetype") or {}).get("name") or ""),
                }
            )
    return rows


def _is_epic(issuetype: str) -> bool:
    return "epic" in (issuetype or "").lower()


def keep_technical_epic_keys(
    keys: list[str],
    issuetypes: dict[str, str] | None,
) -> tuple[list[str], list[str]]:
    """WEBCL (and similar) keys can be NCO or Bug; generation only uses Epic types.

    Unknown keys (Jira down / 404) stay in the list — fail open.
    """
    types = issuetypes or {}
    if not types:
        return list(keys), []
    kept: list[str] = []
    dropped: list[str] = []
    for key in keys:
        name = (types.get(key) or "").strip()
        if name and not _is_epic(name):
            dropped.append(key)
        else:
            kept.append(key)
    return kept, dropped


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


_SCOPE_FIELDS = [
    "summary",
    "description",
    "issuetype",
    "status",
    "priority",
    "versions",
    "fixVersions",
]
_SCOPE_TIMEOUT = 45.0


def _unique_issue_keys(keys: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for key in keys:
        normalized = (key or "").strip().upper()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique


def _version_names(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    names: list[str] = []
    for item in value:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            if name:
                names.append(name)
        elif item:
            names.append(str(item).strip())
    return ", ".join(names)


def fetch_scope_fields_for_keys(keys: list[str]) -> dict[str, dict[str, str]]:
    """Batch Jira lookup for RN-scope Excel columns. Empty if Jira is missing.

    Does not load epics, children, or Gherkin. Used only by Extraer alcance RN.
    """
    unique = _unique_issue_keys(keys)
    if not unique:
        return {}
    try:
        client_cm = _client(timeout=_SCOPE_TIMEOUT)
    except JiraNotConfiguredError:
        return {}

    found: dict[str, dict[str, str]] = {}
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
                        "fields": list(_SCOPE_FIELDS),
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
                        if not key:
                            continue
                        found[key] = {
                            "summary": str(fields.get("summary") or "").strip(),
                            "description": adf_to_text(fields.get("description"))[:4000],
                            "issuetype": ((fields.get("issuetype") or {}).get("name") or "").strip(),
                            "status": ((fields.get("status") or {}).get("name") or "").strip(),
                            "priority": ((fields.get("priority") or {}).get("name") or "").strip(),
                            "affected_versions": _version_names(fields.get("versions")),
                            "fix_versions": _version_names(fields.get("fixVersions")),
                        }
                    next_page_token = payload.get("nextPageToken") or None
                    if not next_page_token:
                        break
    except (JiraApiError, httpx.TimeoutException, httpx.RequestError):
        return found
    return found


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


def _is_product_epic(issuetype: str) -> bool:
    return "product epic" in (issuetype or "").lower()


def _is_user_story_type(issuetype: str) -> bool:
    kind = (issuetype or "").strip().lower()
    return kind in {"user story", "historia de usuario"} or kind.startswith("user story")


def collect_user_stories(
    technical_brief: dict[str, Any] | None,
    brief_children: list[dict[str, Any]],
    children_by_epic: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """User Stories live under Product Epics of the Product Brief, not on the Technical Epic.

    Technical Epic → parent TBRFRE → parent BRFRE → Product Epic children → User Story children.
    """
    if not isinstance(technical_brief, dict):
        return []
    product_key = str(technical_brief.get("parent_key") or "").strip()
    if not product_key:
        return []
    stories: list[dict[str, Any]] = []
    for child in brief_children:
        if not isinstance(child, dict) or not _is_product_epic(str(child.get("issuetype") or "")):
            continue
        epic_key = str(child.get("key") or "").strip()
        for story in children_by_epic.get(epic_key) or []:
            if isinstance(story, dict) and _is_user_story_type(str(story.get("issuetype") or "")):
                stories.append(story)
    return stories


def _attach_user_story(client, artifact: dict[str, Any]) -> None:
    """Load every User Story of the Product Brief. The model drops the ones from another epic."""
    artifact["user_stories"] = []
    artifact["user_story"] = None
    parent_key = str(artifact.get("parent_key") or "").strip()
    if not parent_key:
        return
    try:
        brief_raw = _get_issue(client, parent_key)
    except JiraApiError:
        return
    if brief_raw is None:
        return
    brief = _issue_payload(brief_raw)
    product_key = str(brief.get("parent_key") or "").strip()
    if not product_key:
        return
    try:
        product_children = [_issue_payload(item) for item in _search_children(client, product_key)]
    except JiraApiError:
        return
    children_by_epic: dict[str, list[dict[str, Any]]] = {}
    for epic in product_children:
        if not _is_product_epic(str(epic.get("issuetype") or "")):
            continue
        epic_key = str(epic.get("key") or "").strip()
        if not epic_key:
            continue
        try:
            children_by_epic[epic_key] = [_issue_payload(item) for item in _search_children(client, epic_key)]
        except JiraApiError:
            children_by_epic[epic_key] = []
    stories = collect_user_stories(brief, product_children, children_by_epic)
    artifact["user_stories"] = stories
    artifact["product_brief_key"] = product_key
    artifact["user_story"] = stories[0] if stories else None


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
                children = [_issue_payload(child) for child in children_raw]
                artifact["children"] = children
                _attach_user_story(client, artifact)
                artifact["child_count"] = len(children_raw)
                artifact["feature_child_count"] = sum(
                    1
                    for child in children
                    if _is_feature_summary(child.get("summary") or "")
                )
                artifacts.append(artifact)
    except JiraApiError:
        return artifacts
    return artifacts
