"""Classify Jira status into Graph 1 buckets and Graph 2 open/closed."""

from __future__ import annotations

import re
from typing import Literal

Bucket = Literal["todo", "testing", "closed", "development"]

_WS = re.compile(r"\s+")

_TODO = {"to do", "tareas por hacer"}
_TESTING_CANONICAL = {
    "integration": "Integration",
    "qa validation": "QA Validation",
    "qc validation": "QC Validation",
    "validate qc": "QC Validation",
    "validation": "QC Validation",
}
_CLOSED_CANONICAL = {
    "roll out": "Roll Out",
    "roll-out": "Roll Out",
    "rollout": "Roll Out",
    "done": "Done",
    "canceled": "Canceled",
    "cancelled": "Canceled",
    "cancelado": "Canceled",
    "cancelada": "Canceled",
    "finalizada": "Finalizada",
    "finalizado": "Finalizada",
    "closed": "Closed",
    "cerrado": "Cerrado",
    "cerrada": "Cerrado",
    "data validation": "Data Validation",
}


def normalize_label(text: str | None) -> str:
    return _WS.sub(" ", (text or "").strip().lower())


def is_technical_epic(issuetype: str | None) -> bool:
    return normalize_label(issuetype) == "technical epic"


def is_blocker_priority(priority: str | None) -> bool:
    key = normalize_label(priority)
    return "blocker" in key or "impedimento" in key or "bloqueador" in key


def is_closed_status(status: str | None, category_key: str | None = None) -> bool:
    bucket, _ = classify_status(status, category_key)
    return bucket == "closed"


def classify_status(status: str | None, category_key: str | None = None) -> tuple[Bucket, str]:
    """Return (bucket, display label). Jira Done category counts as closed."""
    raw = (status or "").strip() or "Sin estado"
    key = normalize_label(raw)
    if key in _TODO:
        return "todo", "To Do"
    if key in _TESTING_CANONICAL:
        return "testing", _TESTING_CANONICAL[key]
    if key in _CLOSED_CANONICAL:
        return "closed", _CLOSED_CANONICAL[key]
    if normalize_label(category_key) == "done":
        return "closed", raw
    return "development", raw
