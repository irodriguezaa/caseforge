"""Sprint pack export allowlist: emails and SWF ids from env (read at request time)."""

from __future__ import annotations

import os

from app.services.sprint_testing.catalog import SWFS, SwfDef, get_swf

_DEFAULT_SWFS = "hitss,neoris"


def pack_emails() -> list[str]:
    raw = os.getenv("SPRINT_PACK_EMAILS", "")
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def pack_email_allowed(email: str | None) -> bool:
    wanted = (email or "").strip().lower()
    allowed = pack_emails()
    return bool(wanted and allowed and wanted in allowed)


def pack_swfs() -> list[SwfDef]:
    raw = (os.getenv("SPRINT_PACK_SWFS") or _DEFAULT_SWFS).strip() or _DEFAULT_SWFS
    found: list[SwfDef] = []
    seen: set[str] = set()
    for item in raw.split(","):
        swf = get_swf(item)
        if swf is None or swf.id in seen:
            continue
        seen.add(swf.id)
        found.append(swf)
    return found or [item for item in SWFS if item.id in {"hitss", "neoris"}]
