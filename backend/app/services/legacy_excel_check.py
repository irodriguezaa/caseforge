"""Chequeo del Excel de Legacy. Las reglas son las mismas que arma el caso."""

from __future__ import annotations

import re
from typing import Any

from app.services.legacy_qc import (
    clause_reflected,
    clean_title,
    echo_pair,
    fold,
    is_entry_action,
    is_filler_expected,
    technical_phrase,
    visible_then_clauses,
)

_FIRST = re.compile(
    r"\b(yo|estoy|soy|mi|nosotros|que tengo|me encuentro|identifico)\b",
    re.IGNORECASE,
)
_KEY_OR_CODE = re.compile(
    r"\bllave\b|c[oó]digo de error|c[oó]digo\s*200|\bPGS_[A-Z0-9_]+\b|la respuesta contiene",
    re.IGNORECASE,
)
_GHERKIN_PRE = re.compile(
    r"(?:^|;)\s*(and|y|given|dado|when|cuando|then|entonces)\b",
    re.IGNORECASE,
)
_PAY_FLOW = re.compile(r"m[eé]todo de pago|suscrip", re.IGNORECASE)
_ACCOUNT = re.compile(
    r"suscrip|m[eé]todo de pago|sesi[oó]n|el usuario (es|tiene|no tiene)",
    re.IGNORECASE,
)
_FILLER_TEXT = re.compile(
    r"la pantalla queda en el estado siguiente|queda seleccionado",
    re.IGNORECASE,
)
_JUNK_PRE = re.compile(r"^(y|and)\.?$", re.IGNORECASE)
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
        "resultado_eco": [],
        "verificar_repetido": [],
        "acciones_sin_resultado": [],
        "llave_o_codigo_en_pre": [],
        "precondicion_vacia": [],
        "unico_verificar": [],
        "acciones_duplicadas": [],
        "pre_sin_cuenta": [],
        "relleno": [],
        "gherkin_en_pre": [],
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
        if any(_FIRST.search(field or "") for field in (pre, *steps, *results)):
            issues["primera_persona"].append(name)
        if any(_cut(field) for field in (name, pre, *steps, *results)):
            issues["texto_cortado"].append(name)
        for action, result in zip(steps, results):
            if echo_pair(action, result):
                issues["resultado_eco"].append(name)
                break
        verify = [action for action in steps if fold(action) == fold("Verificar el resultado")]
        if len(verify) > 1:
            issues["verificar_repetido"].append(name)
        for left_action, left_result, right_action in zip(steps, results, steps[1:]):
            if echo_pair(left_action, left_result) or not (left_result or "").strip():
                if left_action and right_action:
                    issues["acciones_sin_resultado"].append(name)
                    break
        clauses = [part.strip() for part in re.split(r"\s*;\s*", pre) if part.strip()]
        if _KEY_OR_CODE.search(pre):
            issues["llave_o_codigo_en_pre"].append(name)
        if any(_JUNK_PRE.match(part.strip(" .")) for part in clauses) or (pre.strip() and not clauses):
            issues["precondicion_vacia"].append(name)
        if len(steps) == 1 and fold(steps[0]).startswith("verificar"):
            issues["unico_verificar"].append(name)
        for left, right, left_result, right_result in zip(steps, steps[1:], results, results[1:]):
            if fold(left) == fold(right) and fold(left_result) == fold(right_result):
                issues["acciones_duplicadas"].append(name)
                break
        if _PAY_FLOW.search(f"{name} {scenario}") and not _ACCOUNT.search(pre):
            issues["pre_sin_cuenta"].append(name)
        if any(_FILLER_TEXT.search(result) or is_filler_expected(action, result) for action, result in zip(steps, results)):
            issues["relleno"].append(name)
        if _GHERKIN_PRE.search(pre):
            issues["gherkin_en_pre"].append(name)
        if body:
            missing = [
                clause
                for clause in visible_then_clauses(body)
                if not clause_reflected(clause, " ".join([*steps, *results]))
            ]
            if missing:
                issues["then_no_reflejado"].append(f"{name}: {missing[0][:80]}")
    return issues
