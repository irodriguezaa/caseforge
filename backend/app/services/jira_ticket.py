"""Normalize pasted Jira keys or browse URLs into KEY-123 | KEY-124."""

from __future__ import annotations

import re

_JIRA_KEY = re.compile(r"\b([A-Z][A-Z0-9_]+-\d+)\b", re.IGNORECASE)


def normalize_jira_tickets(raw: str | None) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None
    found: list[str] = []
    seen: set[str] = set()
    for match in _JIRA_KEY.finditer(text):
        key = match.group(1).upper()
        if key in seen:
            continue
        seen.add(key)
        found.append(key)
    if found:
        return " | ".join(found)
    return text[:250]
