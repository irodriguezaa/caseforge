"""Optional Jira + Confluence context for a selected BRF."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.jira_generation import (
    JiraApiError,
    JiraNotConfiguredError,
    _client,
    _get_issue,
    _issue_payload,
    _search_children,
    adf_to_text,
)
from app.services.operativa_engine.confluence import (
    ConfluencePage,
    fetch_brf_confluence_text,
    fetch_issue_remotelinks,
)


@dataclass
class BrfContextBundle:
    brf_key: str
    jira_blob: str
    confluence_page_id: str | None = None
    confluence_title: str | None = None
    confluence_blob: str = ""
    combined_blob: str = ""
    hn_source: str = "HN_ABSENT"

    def __post_init__(self) -> None:
        if not self.combined_blob:
            parts = [self.jira_blob]
            if self.confluence_blob:
                header = f"=== CONFLUENCE {self.brf_key} ==="
                if self.confluence_title:
                    header += f" ({self.confluence_title})"
                parts.append(header)
                parts.append(self.confluence_blob)
            self.combined_blob = "\n".join(part for part in parts if part)
        if self.confluence_blob and re.search(r"\bHN\d{2,4}\b", self.confluence_blob, re.I):
            self.hn_source = "CONFLUENCE"
        elif re.search(r"\bHN\d{2,4}\b", self.jira_blob, re.I):
            self.hn_source = "JIRA"
        else:
            self.hn_source = "HN_ABSENT"


def fetch_brf_context_bundle(brf_key: str) -> BrfContextBundle:
    """Jira issue text plus Confluence BRF page when a remotelink exists."""
    jira_blob = _fetch_jira_blob(brf_key)
    remotelinks = fetch_issue_remotelinks(brf_key)
    confluence = fetch_brf_confluence_text(brf_key, remotelinks, extra_text=jira_blob)
    return BrfContextBundle(
        brf_key=brf_key,
        jira_blob=jira_blob,
        confluence_page_id=confluence.page_id if confluence else None,
        confluence_title=confluence.title if confluence else None,
        confluence_blob=confluence.text if confluence else "",
    )


def fetch_brf_context(brf_key: str) -> str:
    """Backward-compatible combined blob for parsers and legacy callers."""
    return fetch_brf_context_bundle(brf_key).combined_blob


def _fetch_jira_blob(brf_key: str) -> str:
    try:
        client_cm = _client(timeout=30.0)
    except JiraNotConfiguredError:
        return ""
    chunks: list[str] = []
    try:
        with client_cm as client:
            raw = _get_issue(client, brf_key)
            if raw is None:
                return ""
            artifact = _issue_payload(raw)
            chunks.extend(_format_artifact("BRF", artifact))
            try:
                children = _search_children(client, brf_key)
            except JiraApiError:
                children = []
            for child in children:
                child_payload = _issue_payload(child)
                chunks.extend(_format_artifact("CHILD", child_payload))
                fields = child.get("fields") or {}
                extra_desc = adf_to_text(fields.get("description"))
                if extra_desc and extra_desc not in child_payload.get("description", ""):
                    chunks.append(extra_desc[:4000])
    except JiraApiError:
        return "\n".join(part for part in chunks if part)
    return "\n".join(part for part in chunks if part)


def _format_artifact(kind: str, artifact: dict) -> list[str]:
    key = artifact.get("key") or ""
    issuetype = (artifact.get("issuetype") or "").strip()
    header = f"=== {kind} {key} ===" if not issuetype else f"=== {kind} {key} ({issuetype}) ==="
    summary = artifact.get("summary") or ""
    parts = [header, summary]
    if kind == "CHILD" and summary and not re.search(r"\bHN\d{2,4}\b", summary, re.IGNORECASE):
        if not re.match(r"^EPC-\d+$", key, re.IGNORECASE):
            parts.append(f"{key}: {summary}")
    parts.extend(
        [
            artifact.get("description") or "",
            artifact.get("acceptance_criteria") or "",
            artifact.get("product_brief_summary") or "",
        ]
    )
    device = artifact.get("device") or ""
    if device:
        parts.append(f"Dispositivos: {device}")
    return [part for part in parts if part]
