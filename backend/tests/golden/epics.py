"""Load the original Jira dump for the golden EPCs. Does not rewrite Gherkin."""

from __future__ import annotations

import json
from pathlib import Path

_DIR = Path(__file__).resolve().parent
_DUMP = _DIR / "jira_aaf_legacy_release47.json"
_WIN_DUMP = _DIR / "jira_win_release47.json"

GOLDEN_EPC_KEYS = ("AAFCL-1919", "AAFCL-1940", "AAFCL-1971", "AAFCL-1987")
WIN_EPC_KEYS = ("WINCL-609", "WINCL-619", "WINCL-636")


def load_jira_artifacts(dump: Path | None = None, keys: tuple[str, ...] | None = None) -> list[dict]:
    path = dump or _DUMP
    wanted = keys or GOLDEN_EPC_KEYS
    payload = json.loads(path.read_text(encoding="utf-8"))
    by_key = {row["key"]: row for row in payload}
    missing = [key for key in wanted if key not in by_key]
    if missing:
        raise FileNotFoundError(f"dump Jira incompleto: {missing}")
    return [by_key[key] for key in wanted]


def load_win_jira_artifacts() -> list[dict]:
    return load_jira_artifacts(_WIN_DUMP, WIN_EPC_KEYS)
