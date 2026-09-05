"""Confluence page fetch for Operativas BRF functional source (HN/CA)."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

from app.services.jira_generation import JiraApiError, JiraNotConfiguredError, _client

_PAGE_ID_RE = re.compile(r"pageId=(\d+)|/pages/(\d+)/", re.IGNORECASE)
_BRF_NUM_RE = re.compile(r"BRF[-_]?(\d+)", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class ConfluencePage:
    page_id: str
    title: str
    text: str


def confluence_html_to_text(raw_html: str) -> str:
    """Flatten Confluence storage HTML to plain text suitable for HN parsing."""
    if not raw_html:
        return ""
    text = raw_html
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>", "\n", text)
    text = re.sub(r"(?i)</li>", "\n", text)
    text = re.sub(r"(?i)</tr>", "\n", text)
    text = re.sub(r"(?i)</h[1-6]>", "\n", text)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" +", " ", text)
    return text.strip()


def _brf_aliases(brf_key: str) -> tuple[str, str]:
    match = _BRF_NUM_RE.search(brf_key or "")
    number = match.group(1) if match else (brf_key or "").replace("BRF-", "").replace("BRF_", "")
    return f"BRF-{number}".upper(), f"BRF_{number}".upper()


def _title_matches_brf(title: str, brf_key: str) -> bool:
    blob = (title or "").upper()
    hyphen, underscore = _brf_aliases(brf_key)
    return hyphen in blob or underscore in blob


def _page_id_from_url(url: str) -> str | None:
    match = _PAGE_ID_RE.search(url or "")
    if not match:
        return None
    return match.group(1) or match.group(2)


def extract_page_ids_from_text(text: str) -> list[str]:
    found: list[str] = []
    for match in _PAGE_ID_RE.finditer(text or ""):
        page_id = match.group(1) or match.group(2)
        if page_id and page_id not in found:
            found.append(page_id)
    return found


def extract_brf_page_id(remotelinks: list[dict], brf_key: str) -> str | None:
    """Pick the Confluence page that matches the BRF key in title or URL.

    Titles often use BRF_17849 instead of BRF-17849. Release-notes pages are not HN sources.
    """
    hyphen, underscore = _brf_aliases(brf_key)
    candidates: list[tuple[int, str]] = []
    for link in remotelinks:
        obj = link.get("object") or {}
        title = str(obj.get("title") or "")
        url = str(obj.get("url") or "")
        page_id = _page_id_from_url(url)
        if not page_id:
            continue
        blob = f"{title} {url}".upper()
        score = 0
        if hyphen in blob or underscore in blob:
            score += 10
        if title.upper().startswith(hyphen) or title.upper().startswith(underscore):
            score += 5
        if re.search(r"BRF[-_]\d+", title, re.IGNORECASE):
            score += 1
        if "RELEASE NOTES" in title.upper():
            score -= 25
        candidates.append((score, page_id))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    if candidates[0][0] <= 0:
        return None
    return candidates[0][1]


def fetch_confluence_page(page_id: str) -> ConfluencePage | None:
    try:
        client_cm = _client(timeout=30.0)
    except JiraNotConfiguredError:
        return None
    path = f"/wiki/rest/api/content/{page_id}?expand=body.storage"
    try:
        with client_cm as client:
            response = client.get(path)
            if response.status_code != 200:
                return None
            payload = response.json()
    except JiraApiError:
        return None
    title = str(payload.get("title") or "")
    storage = ((payload.get("body") or {}).get("storage") or {}).get("value") or ""
    return ConfluencePage(page_id=page_id, title=title, text=confluence_html_to_text(storage))


def fetch_brf_confluence_text(
    brf_key: str,
    remotelinks: list[dict] | None = None,
    extra_text: str | None = None,
) -> ConfluencePage | None:
    links = remotelinks
    if links is None:
        links = fetch_issue_remotelinks(brf_key)
    page_id = extract_brf_page_id(links, brf_key)
    if not page_id:
        for candidate in extract_page_ids_from_text(extra_text or ""):
            page = fetch_confluence_page(candidate)
            if page and _title_matches_brf(page.title, brf_key):
                return page
        page_id = _search_confluence_page_id(brf_key)
    if not page_id:
        return None
    return fetch_confluence_page(page_id)


def _search_confluence_page_id(brf_key: str) -> str | None:
    hyphen, underscore = _brf_aliases(brf_key)
    cql = f'(title ~ "{hyphen}" OR title ~ "{underscore}") AND type = page'
    try:
        client_cm = _client(timeout=30.0)
    except JiraNotConfiguredError:
        return None
    try:
        with client_cm as client:
            response = client.get("/wiki/rest/api/content/search", params={"cql": cql, "limit": 10})
            if response.status_code != 200:
                return None
            results = response.json().get("results") or []
    except JiraApiError:
        return None
    scored: list[tuple[int, str]] = []
    for item in results:
        title = str(item.get("title") or "")
        page_id = str(item.get("id") or "")
        if not page_id:
            continue
        score = 10 if _title_matches_brf(title, brf_key) else 0
        if "RELEASE NOTES" in title.upper():
            score -= 25
        if score > 0:
            scored.append((score, page_id))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def fetch_issue_remotelinks(issue_key: str) -> list[dict]:
    try:
        client_cm = _client(timeout=30.0)
    except JiraNotConfiguredError:
        return []
    try:
        with client_cm as client:
            response = client.get(f"/rest/api/3/issue/{issue_key}/remotelink")
            if response.status_code != 200:
                return []
            payload = response.json()
            return payload if isinstance(payload, list) else []
    except JiraApiError:
        return []
