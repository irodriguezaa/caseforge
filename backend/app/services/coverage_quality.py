"""FASE 6A quality gate and applicability. Structural rules only."""

from __future__ import annotations

import re

from app.schemas.case_generation import GeneratedCaseCandidate

_GHERKIN_LEAD = re.compile(
    r"^\s*(Given|When|Then|And|But|Dado que|Dado|Cuando|Entonces|Y|Pero)\b",
    re.IGNORECASE,
)
_LEAD_JUNK = re.compile(r"^\s*(\||#{1,6}\s|[-*]\s|[^\wÁÉÍÓÚáéíóúñÑ])")
_PLACEHOLDER = re.compile(r"<[A-Za-zÁ-ú_]+>")
_EMPTY_TABLE = re.compile(r"\|[^|]+\|[^|]+\|\s*$")
_MARKDOWN_RESIDUE = re.compile(r"```|\"\"\"|__")
_USER_EXPECTED = re.compile(r"^\s*(el )?usuario\b", re.IGNORECASE)
_GENERIC_ACTION = "el usuario ingresa al flujo correspondiente"
_REMOTE_GIVEN = re.compile(
    r"(no se (logra |puede )?obtener|"
    r"(vac[ií]a|inexistente|ausente|no (existe|se encuentra|est[aá] presente|est[aá] definida))|"
    r"(forzad[oa]|simulad[oa]|respuesta (fija|controlada)))",
    re.IGNORECASE,
)
_REMOTE_CTX = re.compile(
    r"\b(configuraci[oó]n|backend|servicio|endpoint|flag|par[aá]metro|llave|key)\b",
    re.IGNORECASE,
)
_USER_OBSERVE = re.compile(
    r"^\s*(el )?usuario\s+(visualiza|ve|observa|identifica)\s+(.+)$",
    re.IGNORECASE,
)
_USER_ACT_EXPECTED = re.compile(
    r"^\s*(el )?usuario\s+(ingresa|selecciona|da clic|hace clic|elige|pulsa|abre|navega)\b",
    re.IGNORECASE,
)
_PLACEHOLDER_TOKEN = re.compile(r"<([A-Za-zÁ-úÑñ_][\wÁ-úÑñ]*)>")


def _norm(text: str) -> str:
    return re.sub(r"\W+", " ", (text or "").lower()).strip()


def normalize_precondition(text: str | None) -> str | None:
    parts = [re.sub(r"\s+", " ", part).strip(" .;") for part in (text or "").split(";") if part.strip()]
    unique: list[str] = []
    seen: set[str] = set()
    for part in parts:
        key = _norm(part)
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(part)
    return "; ".join(unique) or None


def given_requires_remote_setup(given_text: str) -> bool:
    blob = given_text or ""
    return bool(_REMOTE_CTX.search(blob) and _REMOTE_GIVEN.search(blob))


def rewrite_expected(text: str | None, fallback: str | None = None) -> str:
    raw = re.sub(r"\s*\|.*$", "", (text or "")).strip()
    raw = _PLACEHOLDER_TOKEN.sub(r"\1", raw)
    match = _USER_OBSERVE.match(raw)
    if match:
        verb = match.group(2).lower()
        rest = match.group(3).strip()
        mapped = {"visualiza": "visualiza", "ve": "ve", "observa": "observa", "identifica": "identifica"}
        return f"Se {mapped.get(verb, 'visualiza')} {rest}".strip()
    if _USER_ACT_EXPECTED.match(raw):
        alt = re.sub(r"\s*\|.*$", "", (fallback or "")).strip()
        if alt and not _USER_EXPECTED.match(alt) and _norm(alt) != _norm(raw):
            return rewrite_expected(alt)
        rest = _USER_ACT_EXPECTED.sub("", raw).strip(" .")
        return f"Se observa {rest}" if rest else (fallback or raw)
    if _USER_EXPECTED.match(raw):
        rest = re.sub(r"^\s*(el )?usuario\s+", "", raw, flags=re.I).strip()
        return f"Se verifica que el usuario {rest}" if rest else raw
    return raw


def looks_like_invalid_lead(text: str | None) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    return bool(_GHERKIN_LEAD.match(raw) or _LEAD_JUNK.match(raw))


def quality_gate(candidates: list[GeneratedCaseCandidate]) -> list[GeneratedCaseCandidate]:
    """Mark failing cases; does not drop them. Zephyr skips quality-gate and na_ambiente."""
    grouped: dict[str, list[GeneratedCaseCandidate]] = {}
    for candidate in candidates:
        grouped.setdefault(_norm(candidate.name), []).append(candidate)
    for rows in grouped.values():
        if len(rows) < 2:
            continue
        for candidate in rows:
            tag = (candidate.related_jira or "").strip()
            cid = next((item for item in (candidate.covers or []) if item), "")
            ctx = ((candidate.precondition or "").split(";")[0] if candidate.precondition else "").strip()[:48]
            suffix = " ".join(part for part in (tag, cid, ctx) if part)[:72]
            if suffix and suffix.lower() not in (candidate.name or "").lower():
                candidate.name = f"{candidate.name} [{suffix}]"[:250]
    for candidate in candidates:
        candidate.precondition = _PLACEHOLDER_TOKEN.sub(r"\1", normalize_precondition(candidate.precondition) or "") or None
        candidate.test_data = _PLACEHOLDER_TOKEN.sub(r"\1", candidate.test_data or "") or candidate.test_data
        candidate.name = _PLACEHOLDER_TOKEN.sub(r"\1", candidate.name or "")
        merged: list = []
        composed = (candidate.generation_origin or "") in {"composed-flow", "llm", "coverage-fill"}
        for step in candidate.steps:
            step.action = _PLACEHOLDER_TOKEN.sub(r"\1", step.action or "")
            step.expected_result = rewrite_expected(step.expected_result, candidate.name)
            same_action = merged and _norm(merged[-1].action) == _norm(step.action)
            same_cover = merged and list(merged[-1].covered_unit_ids or []) == list(step.covered_unit_ids or [])
            if same_action and (same_cover or not composed):
                merged[-1].expected_result = f"{merged[-1].expected_result}; {step.expected_result}".strip("; ")
                continue
            merged.append(step)
        candidate.steps = merged
        for index, step in enumerate(candidate.steps, start=1):
            step.step_number = index
            if _norm(step.expected_result) == _norm(candidate.name) and step.expected_result:
                ctx = (candidate.related_jira or "").strip()
                if ctx and ctx.lower() not in (candidate.name or "").lower():
                    candidate.name = f"{candidate.name} ({ctx})"[:250]
        reasons: list[str] = []
        blob = " ".join(
            [
                candidate.name or "",
                candidate.precondition or "",
                candidate.test_data or "",
            ]
            + [f"{step.action} {step.expected_result}" for step in candidate.steps]
        )
        if looks_like_invalid_lead(candidate.name):
            reasons.append("titulo-gherkin")
        for step in candidate.steps:
            if looks_like_invalid_lead(step.action) or looks_like_invalid_lead(step.expected_result):
                reasons.append("paso-gherkin")
            if _USER_EXPECTED.match(step.expected_result or ""):
                reasons.append("esperado-es-accion")
            if _norm(step.expected_result) == _norm(candidate.name):
                reasons.append("esperado-es-titulo")
            givens = [_norm(part) for part in (candidate.precondition or "").split(";") if part.strip()]
            if _norm(step.expected_result) in givens:
                reasons.append("esperado-es-given")
        acts = [_norm(step.action) for step in candidate.steps]
        if acts and all(item == _GENERIC_ACTION for item in acts):
            reasons.append("pasos-genericos")
        if any(acts[index] == acts[index + 1] for index in range(len(acts) - 1)):
            reasons.append("accion-repetida")
        if _PLACEHOLDER.search(blob):
            reasons.append("placeholder")
        if any(_EMPTY_TABLE.search(step.expected_result or "") for step in candidate.steps):
            reasons.append("tabla-vacia")
        if _MARKDOWN_RESIDUE.search(blob):
            reasons.append("markdown")
        pre = [_norm(part) for part in (candidate.precondition or "").split(";") if part.strip()]
        if len(pre) != len(set(pre)):
            reasons.append("precondicion-duplicada")
        if reasons:
            candidate.review_required = True
            candidate.applied_rules = list(
                dict.fromkeys(
                    [*(candidate.applied_rules or []), *[f"quality-gate:{item}" for item in reasons]]
                )
            )
    return candidates


def skip_zephyr_export(candidate: GeneratedCaseCandidate | object) -> bool:
    rules = getattr(candidate, "applied_rules", None) or []
    if any(str(rule).startswith("quality-gate:") for rule in rules):
        return True
    applicability = getattr(candidate, "applicability", None)
    reason = getattr(candidate, "applicability_reason", None) or ""
    if applicability == "na_ambiente" or str(reason).startswith("na_ambiente"):
        return True
    return False
