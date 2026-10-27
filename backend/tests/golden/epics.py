"""Load the original Jira dump for the golden EPCs. Does not rewrite Gherkin."""

from __future__ import annotations

import json
from pathlib import Path

_DUMP = Path(__file__).resolve().parent / "jira_aaf_legacy_release47.json"

GOLDEN_EPC_KEYS = ("AAFCL-1919", "AAFCL-1940", "AAFCL-1971", "AAFCL-1987")


def load_jira_artifacts() -> list[dict]:
    payload = json.loads(_DUMP.read_text(encoding="utf-8"))
    by_key = {row["key"]: row for row in payload}
    missing = [key for key in GOLDEN_EPC_KEYS if key not in by_key]
    if missing:
        raise FileNotFoundError(f"dump Jira incompleto: {missing}")
    return [by_key[key] for key in GOLDEN_EPC_KEYS]
