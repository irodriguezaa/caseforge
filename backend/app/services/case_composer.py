"""Compose CoverageUnits of one story into executable user flows.

Inventory says what to cover. This module decides how to group it and how to write it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.schemas.case_generation import CandidateStep, CoverageUnit, GeneratedCaseCandidate
from app.services.coverage_quality import normalize_precondition, rewrite_expected
from app.services.executability import is_user_action, parse_scenario_clauses

_GENERIC = re.compile(
    r"^\s*(el usuario\s+)?ingresa al flujo correspondiente\.?\s*$",
    re.IGNORECASE,
)
_TITLE_PREFIX = re.compile(
    r"^\s*(validar|verificar que|verificar|scenario outline|scenario|comprobar que|comprobar)\s*[:.]?\s*",
    re.IGNORECASE,
)
_USER = re.compile(r"^\s*(el )?usuario\s+", re.IGNORECASE)
_3SG = (
    (re.compile(r"\bselecciona\b", re.I), "Seleccionar"),
    (re.compile(r"\bingresa( a| al|)\b", re.I), "Ingresar"),
    (re.compile(r"\babre\b", re.I), "Abrir"),
    (re.compile(r"\bcierra\b", re.I), "Cerrar"),
    (re.compile(r"\bpresiona\b", re.I), "Presionar"),
    (re.compile(r"\bnavega\b", re.I), "Navegar"),
    (re.compile(r"\bda clic\b", re.I), "Hacer clic"),
    (re.compile(r"\bhace clic\b", re.I), "Hacer clic"),
    (re.compile(r"\belige\b", re.I), "Elegir"),
    (re.compile(r"\bpulsa\b", re.I), "Pulsar"),
    (re.compile(r"\bconfirma\b", re.I), "Confirmar"),
    (re.compile(r"\bcancela\b", re.I), "Cancelar"),
    (re.compile(r"\breproduce\b", re.I), "Reproducir"),
    (re.compile(r"\bbusca\b", re.I), "Buscar"),
    (re.compile(r"\bvisualiza\b", re.I), "Visualizar"),
)
_NEGATIVE = re.compile(r"inv[aá]lid|error|mensaje|rechaz|no se (muestra|permite)|incorrect", re.I)
_SUCCESS = re.compile(r"\b(éxito|exito|correct|permite|se muestra|se inicia|confirma)\b", re.I)
_STOP = {
    "el",
    "la",
    "los",
    "las",
    "un",
    "una",
    "de",
    "del",
    "en",
    "al",
    "se",
    "que",
    "con",
    "por",
    "para",
    "cuando",
    "usuario",
    "then",
    "when",
    "given",
    "and",
}


def _norm(text: str | None) -> str:
    return re.sub(r"\W+", " ", (text or "").lower()).strip()


def _tokens(text: str | None) -> set[str]:
    return {tok for tok in _norm(text).split() if len(tok) > 2 and tok not in _STOP}


def phrases_similar(left: str | None, right: str | None) -> bool:
    a, b = _norm(left), _norm(right)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= 0.42


def to_infinitive(action: str | None) -> str:
    raw = re.sub(r"\s+", " ", (action or "").strip().rstrip("."))
    raw = _USER.sub("", raw)
    if not raw:
        return ""
    for pattern, replacement in _3SG:
        if pattern.search(raw):
            raw = pattern.sub(replacement, raw, count=1)
            break
    else:
        raw = raw[0].upper() + raw[1:] if raw else raw
    if raw and raw[0].islower():
        raw = raw[0].upper() + raw[1:]
    return raw


def strip_title_prefix(name: str | None) -> str:
    out = (name or "").strip()
    out = _TITLE_PREFIX.sub("", out).strip()
    return out[:250] or (name or "").strip()[:250]


def _clauses(unit: CoverageUnit) -> dict[str, list[str]]:
    parsed = parse_scenario_clauses(unit.body or "")
    if unit.user_action:
        parsed["actions"] = list(dict.fromkeys([unit.user_action, *parsed["actions"]]))
    if unit.observable_then:
        parsed["expected"] = list(dict.fromkeys([*unit.observable_then, *parsed["expected"]]))
    return parsed


def _unit_action(unit: CoverageUnit) -> str:
    parsed = _clauses(unit)
    for item in parsed.get("actions") or []:
        text = to_infinitive(item)
        if text and not _GENERIC.match(text):
            return text
    if unit.user_action:
        text = to_infinitive(unit.user_action)
        if text and not _GENERIC.match(text):
            return text
    return ""


def _unit_expected(unit: CoverageUnit) -> str:
    parsed = _clauses(unit)
    parts = [item for item in (parsed.get("expected") or []) if item.strip()]
    blob = "; ".join(dict.fromkeys(parts))
    return rewrite_expected(blob, unit.scenario)


def _unit_given(unit: CoverageUnit) -> str:
    parsed = _clauses(unit)
    return "; ".join(parsed.get("given") or [])


def _follows(previous: CoverageUnit, nxt: CoverageUnit) -> bool:
    if (previous.story_key or "") != (nxt.story_key or ""):
        return False
    if _same_expected(previous, nxt) and phrases_similar(
        _unit_action(previous) or previous.user_action, _unit_action(nxt) or nxt.user_action
    ):
        return True
    given = _unit_given(nxt)
    if not given:
        return phrases_similar(previous.user_action, nxt.user_action) and phrases_similar(
            _unit_expected(previous), _unit_expected(nxt)
        ) is False
    return any(
        phrases_similar(given, seed)
        for seed in (
            _unit_action(previous),
            _unit_expected(previous),
            previous.scenario,
            previous.user_action,
        )
        if seed
    )


def _exclusive_precondition(left: CoverageUnit, right: CoverageUnit) -> bool:
    a, b = _norm(_unit_given(left) or left.normal_precondition), _norm(
        _unit_given(right) or right.normal_precondition
    )
    if not a or not b or a == b:
        return False
    return (" no " in f" {a} ") != (" no " in f" {b} ") or (
        ("sin " in a) != ("sin " in b)
    )


def _recoverable(previous: CoverageUnit, nxt: CoverageUnit) -> bool:
    return bool(_NEGATIVE.search(_unit_expected(previous) or "")) and bool(
        _SUCCESS.search(_unit_expected(nxt) or "")
    )


def _same_expected(left: CoverageUnit, right: CoverageUnit) -> bool:
    return _norm(_unit_expected(left)) == _norm(_unit_expected(right)) and bool(
        _norm(_unit_expected(left))
    )


@dataclass
class FlowDraft:
    story_key: str
    epic_key: str
    units: list[CoverageUnit]
    title: str
    precondition: str | None
    steps: list[CandidateStep]
    test_data: str | None
    pending_reason: str | None = None
    evidence: str = ""
    applied_rules: list[str] = field(default_factory=list)


def _group_same_when(units: list[CoverageUnit]) -> list[list[CoverageUnit]]:
    groups: list[list[CoverageUnit]] = []
    for unit in units:
        action = _norm(_unit_action(unit))
        expected = _norm(_unit_expected(unit))
        if groups:
            last = groups[-1]
            last_action = _norm(_unit_action(last[0]))
            last_expected = _norm(_unit_expected(last[0]))
            if action and action == last_action and expected == last_expected:
                last.append(unit)
                continue
            if action and action == last_action and not _exclusive_precondition(last[0], unit):
                last.append(unit)
                continue
        groups.append([unit])
    return groups


def _draft_title(units: list[CoverageUnit]) -> str:
    last = units[-1]
    action = to_infinitive(_unit_action(units[0]) or units[0].user_action or "")
    expected = strip_title_prefix(_unit_expected(last) or last.scenario or last.behavior)
    ctx = strip_title_prefix((units[0].normal_precondition or "").split(";")[0] if units[0].normal_precondition else "")
    pieces = [part for part in (action, expected) if part]
    title = " — ".join(pieces) if action and expected and _norm(action) != _norm(expected) else expected
    if ctx and _norm(ctx) not in _norm(title) and not ctx.lower().startswith("feature"):
        title = f"{title} ({ctx})"
    elif ctx.lower().startswith("feature") and ctx not in title:
        title = f"{title} ({ctx[:80]})"
    title = strip_title_prefix(title)
    if _norm(title) == _norm(expected) and action:
        title = action
    story = units[0].story_key or last.coverage_id
    title = f"{title[:180]} [{story}]"
    return title[:250]


def _draft_from_units(units: list[CoverageUnit]) -> FlowDraft:
    story = units[0].story_key or units[0].jira_key or ""
    epic = units[0].artifact_key or units[0].rn_key or ""
    groups = _group_same_when(units)
    steps: list[CandidateStep] = []
    pending = None
    extras: list[str] = []
    pres: list[str] = []
    first_given = _unit_given(units[0])
    for clause in [part.strip() for part in (first_given or "").split(";") if part.strip()]:
        if is_user_action(clause) and not phrases_similar(clause, _unit_action(units[0])):
            steps.append(
                CandidateStep(
                    step_number=1,
                    action=to_infinitive(clause),
                    expected_result=rewrite_expected(_unit_expected(units[0]), units[0].scenario),
                    covered_unit_ids=[units[0].coverage_id],
                )
            )
            break
        pres.append(clause)
    for group in groups:
        action = _unit_action(group[0])
        expected = "; ".join(dict.fromkeys(_unit_expected(item) for item in group if _unit_expected(item)))
        quoted = re.findall(
            r'["\u201c]([^"\u201d\n]{2,80})["\u201d]',
            " ".join(item.body or "" for item in group),
        )
        for quote in quoted:
            if quote.lower() not in (expected or "").lower() and quote.lower() not in (action or "").lower():
                expected = f'{expected} "{quote}"'.strip() if expected else f'"{quote}"'
        covers = [item.coverage_id for item in group]
        extras.extend(item.extra_test_data or "" for item in group)
        extras.extend(note for item in group for note in (item.technical_notes or []))
        pres.extend(filter(None, [_unit_given(item) for item in group]))
        pres.extend(filter(None, [item.normal_precondition for item in group]))
        if not action:
            pending = "sin acción de usuario soportable en las unidades cubiertas"
            action = to_infinitive(group[0].scenario) or strip_title_prefix(group[0].behavior)
        steps.append(
            CandidateStep(
                step_number=len(steps) + 1,
                action=action,
                expected_result=expected or rewrite_expected(group[0].scenario),
                covered_unit_ids=covers,
            )
        )
    precondition = normalize_precondition("; ".join(pres))
    literals = []
    for unit in units:
        literals.extend(
            f'"{quote}"'
            for quote in re.findall(
                r'["\u201c]([^"\u201d\n]{2,80})["\u201d]',
                f"{unit.body or ''}\n{unit.evidence or ''}\n{unit.description or ''}",
            )
        )
    extras.extend(literals)
    test_data = "; ".join(dict.fromkeys(part for part in extras if part)) or None
    evidence = " | ".join(dict.fromkeys((unit.evidence or "").split("\n", 1)[0] for unit in units))[:2000]
    return FlowDraft(
        story_key=story,
        epic_key=epic,
        units=units,
        title=_draft_title(units),
        precondition=precondition,
        steps=steps,
        test_data=test_data,
        pending_reason=pending,
        evidence=evidence,
        applied_rules=["composed-flow"],
    )


def _intent_verb(unit: CoverageUnit) -> str:
    action = to_infinitive(_unit_action(unit) or unit.user_action or "")
    return (action.split() or [""])[0].lower()


def compose_story_units(units: list[CoverageUnit]) -> list[FlowDraft]:
    ordered = list(units)
    if not ordered:
        return []
    segments: list[list[CoverageUnit]] = [[ordered[0]]]
    for nxt in ordered[1:]:
        prev = segments[-1][-1]
        if _exclusive_precondition(prev, nxt) and not _recoverable(prev, nxt):
            segments.append([nxt])
            continue
        if _follows(prev, nxt) or _recoverable(prev, nxt) or _same_expected(prev, nxt):
            segments[-1].append(nxt)
            continue
        prev_intent, next_intent = _intent_verb(prev), _intent_verb(nxt)
        if prev_intent and next_intent and prev_intent != next_intent and not phrases_similar(
            _unit_expected(prev), _unit_given(nxt)
        ):
            segments.append([nxt])
            continue
        segments[-1].append(nxt)
    drafts = [_draft_from_units(segment) for segment in segments]
    if len(drafts) > 1:
        for index, draft in enumerate(drafts, start=1):
            marker = f"flujo {index}"
            if marker not in (draft.title or "").lower():
                draft.title = f"{draft.title} ({marker})"[:250]
    return drafts


def draft_to_candidate(
    draft: FlowDraft,
    existing: list[dict[str, str]],
    duplicate_of,
) -> GeneratedCaseCandidate:
    covers = [unit.coverage_id for unit in draft.units]
    review = True
    rules = list(draft.applied_rules)
    if draft.pending_reason:
        rules.append(f"pendiente-qc:{draft.pending_reason}")
    return GeneratedCaseCandidate(
        name=draft.title,
        description=draft.title,
        precondition=draft.precondition,
        steps=draft.steps,
        test_data=draft.test_data,
        related_functionality=draft.epic_key or None,
        related_jira=draft.story_key or None,
        related_rn=draft.units[0].rn_filename if draft.units else None,
        evidence=draft.evidence or draft.title,
        justification="Flujo compuesto a partir de CoverageUnits de la misma historia.",
        possible_duplicate_of=duplicate_of(draft.title, draft.story_key, existing),
        review_required=review,
        covers=covers,
        covered_unit_ids=covers,
        applicability=draft.units[0].applicability if draft.units else "ejecutable",
        applicability_reason=draft.pending_reason or (
            draft.units[0].applicability_reason if draft.units else None
        ),
        applied_rules=rules,
        generation_origin="composed-flow",
        source_type="functionality",
        confidence="medium" if draft.pending_reason else "high",
    )


def attach_artifact_literals(
    candidates: list[GeneratedCaseCandidate],
    artifacts: list[dict] | None,
) -> list[GeneratedCaseCandidate]:
    if not artifacts:
        return candidates
    quotes_by_story: dict[str, list[str]] = {}
    for art in artifacts:
        nodes = [art, *(art.get("children") or [])]
        for node in nodes:
            key = str(node.get("key") or "")
            blob = f"{node.get('description') or ''}\n{node.get('acceptance_criteria') or ''}"
            found = [
                f'"{quote}"'
                for quote in re.findall(r'["\u201c]([^"\u201d\n]{2,80})["\u201d]', blob)
                if not re.search(r"[/_{}\[\]]", quote)
            ]
            if key and found:
                quotes_by_story.setdefault(key, []).extend(found)
        epic_key = str(art.get("key") or "")
        child_quotes = []
        for child in art.get("children") or []:
            child_quotes.extend(quotes_by_story.get(str(child.get("key") or ""), []))
        if epic_key:
            quotes_by_story.setdefault(epic_key, []).extend(child_quotes)
    for candidate in candidates:
        keys = [
            part.strip()
            for part in (
                f"{candidate.related_jira or ''}|{candidate.related_functionality or ''}"
            ).split("|")
            if part.strip()
        ]
        extras: list[str] = []
        for key in keys:
            extras.extend(quotes_by_story.get(key, []))
        if extras:
            candidate.test_data = "; ".join(
                dict.fromkeys(part for part in [candidate.test_data, *extras] if part)
            )
    return candidates


def compose_inventory(
    inventory: list[CoverageUnit],
    existing: list[dict[str, str]],
    duplicate_of,
) -> list[GeneratedCaseCandidate]:
    by_story: dict[str, list[CoverageUnit]] = {}
    order: list[str] = []
    na_units: list[CoverageUnit] = []
    for unit in inventory:
        if (unit.applicability or "ejecutable") == "na_ambiente":
            na_units.append(unit)
            continue
        key = unit.story_key or unit.jira_key or unit.coverage_id
        if key not in by_story:
            order.append(key)
        by_story.setdefault(key, []).append(unit)
    out: list[GeneratedCaseCandidate] = []
    for key in order:
        for draft in compose_story_units(by_story[key]):
            out.append(draft_to_candidate(draft, existing, duplicate_of))
    for unit in na_units:
        draft = _draft_from_units([unit])
        draft.pending_reason = draft.pending_reason or (
            unit.applicability_reason or "na_ambiente"
        )
        candidate = draft_to_candidate(draft, existing, duplicate_of)
        candidate.applicability = "na_ambiente"
        out.append(candidate)
    return out


def proposed_flows_for_llm(units: list[CoverageUnit]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    by_story: dict[str, list[CoverageUnit]] = {}
    for unit in units:
        if (unit.applicability or "ejecutable") == "na_ambiente":
            continue
        by_story.setdefault(unit.story_key or unit.coverage_id, []).append(unit)
    for story_units in by_story.values():
        for draft in compose_story_units(story_units):
            rows.append(
                {
                    "title": draft.title,
                    "precondition": draft.precondition,
                    "story_key": draft.story_key,
                    "covered_unit_ids": [unit.coverage_id for unit in draft.units],
                    "steps": [
                        {
                            "step_number": step.step_number,
                            "action": step.action,
                            "expected_result": step.expected_result,
                            "covered_unit_ids": list(step.covered_unit_ids or []),
                        }
                        for step in draft.steps
                    ],
                }
            )
    return rows


def _observable_blob(unit: CoverageUnit) -> str:
    return _norm(" ".join([*(unit.observable_then or []), _unit_expected(unit), unit.scenario]))


def validate_composed_candidates(
    candidates: list[GeneratedCaseCandidate],
    inventory: list[CoverageUnit],
    *,
    fill_missing,
) -> list[GeneratedCaseCandidate]:
    """Reject or repair LLM/fallback cases against inventory and the writing standard."""
    by_id = {unit.coverage_id: unit for unit in inventory}
    executable_ids = {
        unit.coverage_id
        for unit in inventory
        if (unit.applicability or "ejecutable") != "na_ambiente"
    }
    repaired: list[GeneratedCaseCandidate] = []
    covered: set[str] = set()
    for candidate in candidates:
        stories = {((by_id.get(cid).story_key if by_id.get(cid) else None) or "") for cid in (candidate.covers or candidate.covered_unit_ids or [])}
        stories.discard("")
        epics = {((by_id.get(cid).artifact_key if by_id.get(cid) else None) or "") for cid in (candidate.covers or candidate.covered_unit_ids or [])}
        epics.discard("")
        if len(stories) > 1 or len(epics) > 1:
            candidate.applied_rules = list(
                dict.fromkeys([*(candidate.applied_rules or []), "quality-gate:mezcla-historias"])
            )
            candidate.review_required = True
            continue
        candidate.name = strip_title_prefix(candidate.name)
        new_steps: list[CandidateStep] = []
        for step in candidate.steps:
            ids = list(step.covered_unit_ids or candidate.covers or [])
            units = [by_id[cid] for cid in ids if cid in by_id]
            action = to_infinitive(step.action)
            if units:
                supported = any(
                    phrases_similar(action, _unit_action(unit)) or phrases_similar(action, unit.user_action)
                    for unit in units
                )
                if action and not supported and not any(phrases_similar(action, _unit_given(unit)) for unit in units):
                    action = _unit_action(units[0]) or action
                expected = step.expected_result or ""
                source = _unit_expected(units[0])
                if expected and source and not phrases_similar(expected, source):
                    expected = source
                elif not expected:
                    expected = source
                step.covered_unit_ids = [unit.coverage_id for unit in units]
                covered.update(step.covered_unit_ids)
            if _GENERIC.match(action or ""):
                action = _unit_action(units[0]) if units else ""
            if not action:
                candidate.applied_rules = list(
                    dict.fromkeys(
                        [*(candidate.applied_rules or []), "pendiente-qc:sin acción de usuario soportable"]
                    )
                )
                candidate.review_required = True
            step.action = action
            step.expected_result = rewrite_expected(expected if units else step.expected_result, candidate.name)
            new_steps.append(step)
        candidate.steps = [step for step in new_steps if step.action or step.expected_result]
        for index, step in enumerate(candidate.steps, start=1):
            step.step_number = index
        ids = list(dict.fromkeys([*(candidate.covers or []), *(candidate.covered_unit_ids or [])]))
        for step in candidate.steps:
            ids.extend(step.covered_unit_ids or [])
        candidate.covers = list(dict.fromkeys(ids))
        candidate.covered_unit_ids = list(candidate.covers)
        covered.update(candidate.covers)
        repaired.append(candidate)
    missing = [unit for unit in inventory if unit.coverage_id in executable_ids and unit.coverage_id not in covered]
    if missing and fill_missing is not None:
        extra = fill_missing(missing)
        repaired.extend(extra)
    return repaired
