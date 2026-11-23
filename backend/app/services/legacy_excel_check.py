"""Chequeo del Excel de Legacy. Las reglas son las mismas que arma el caso."""

from __future__ import annotations

import re
from typing import Any

from app.services.legacy_qc import (
    clause_reflected,
    clean_title,
    fold,
    is_entry_action,
    technical_phrase,
    visible_then_clauses,
)

_FIRST = re.compile(r"\b(yo|estoy|soy|mi|nosotros)\b", re.IGNORECASE)
_CUT = re.compile(
    r"\b(de|del|la|el|los|las|un|una|que|al|con|por|para|en|se)$",
    re.IGNORECASE,
)


def _numbered(cell: str) -> list[str]:
    text = (cell or "").strip()
    if not text:
        return []
    parts = re.split(r"\n(?=\d+\.\s)", text)
    return [re.sub(r"^\d+\.\s*", "", part).strip() for part in parts if part.strip()]


def _cut(value: str) -> bool:
    text = (value or "").strip()
    if not text:
        return False
    if text.count("«") != text.count("»"):
        return True
    if text.count('"') % 2:
        return True
    if _CUT.search(text):
        return True
    if len(text) in {120, 180, 500} and re.search(r"[A-Za-zÁÉÍÓÚáéíóúñÑ]$", text):
        return True
    return False


def audit_cases(rows: list[dict[str, Any]], origins: dict[str, str]) -> dict[str, list[str]]:
    """`origins` mapea el nombre del caso al cuerpo del escenario."""
    issues: dict[str, list[str]] = {
        "then_no_reflejado": [],
        "resultado_vacio": [],
        "entrada_duplicada": [],
        "titulo_ajeno": [],
        "palabra_tecnica": [],
        "primera_persona": [],
        "texto_cortado": [],
    }
    for row in rows:
        name = str(row.get("name") or "")
        steps = _numbered(str(row.get("steps") or ""))
        results = _numbered(str(row.get("results") or ""))
        pre = str(row.get("precondition") or "")
        scenario = str(row.get("scenario") or "")
        body = origins.get(name) or origins.get(fold(name)) or ""
        if len(results) < len(steps):
            results = results + [""] * (len(steps) - len(results))
        if steps and any(not item.strip() for item in results):
            issues["resultado_vacio"].append(name)
        for left, right in zip(steps, steps[1:]):
            if is_entry_action(left) and is_entry_action(right):
                issues["entrada_duplicada"].append(name)
                break
        cleaned = clean_title(scenario) if scenario else ""
        if cleaned and not (
            fold(name).startswith(fold(cleaned)) or fold(cleaned).startswith(fold(name))
        ):
            issues["titulo_ajeno"].append(name)
        blob_fields = [pre, *steps, *results]
        if any(technical_phrase(field) for field in blob_fields if field):
            issues["palabra_tecnica"].append(name)
        if _FIRST.search(pre):
            issues["primera_persona"].append(name)
        if any(_cut(field) for field in (name, pre, *steps, *results)):
            issues["texto_cortado"].append(name)
        if body:
            missing = [
                clause
                for clause in visible_then_clauses(body)
                if not clause_reflected(clause, " ".join(results))
            ]
            if missing:
                issues["then_no_reflejado"].append(f"{name}: {missing[0][:80]}")
    return issues
