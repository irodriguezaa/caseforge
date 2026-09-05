"""Stores the original Release Note PDF so generate-cases can read RN evidence later.

Analyze-rn does not persist to the database; create-release copies analysis_data including
pdf_file_path. No new table: the path lives on the existing release_analyses.pdf_file_path.
"""

import re
import uuid
from pathlib import Path

from app.config import settings


def persist_release_note_pdf(filename: str, content: bytes) -> str | None:
    if not content:
        return None
    root = Path(settings.rn_storage_dir)
    try:
        root.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", filename)[:80] or "release-note.pdf"
        dest = root / f"{uuid.uuid4().hex}_{safe}"
        dest.write_bytes(content)
        return str(dest)
    except OSError:
        return None


def delete_release_note_pdf(path: str | None) -> None:
    if not path:
        return
    try:
        target = Path(path).resolve()
        root = Path(settings.rn_storage_dir).resolve()
        target.relative_to(root)
        if target.is_file():
            target.unlink()
    except (OSError, ValueError):
        return


def read_release_note_pdf(path: str | None) -> bytes | None:
    if not path:
        return None
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    return data or None
