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
    r"^\s*(el usuario\s+)?ingres(a|ar)( al)? flujo correspondiente\.?\s*$",
    re.IGNORECASE,
)
_TITLE_PREFIX = re.compile(
    r"^\s*(validar|verificar que|verificar|scenario outline|scenario|comprobar que|"
    r"comprobar|asegurar que|validaci[oó]n de|crear pantalla)\s*[:.]?\s*",
    re.IGNORECASE,
)
_FEATURE = re.compile(r"\bfeature\s*:?\s*", re.IGNORECASE)
_FLOW_MARK = re.compile(r"\s*(\(flujo\s+\d+\)|\[[A-Z][A-Z0-9]+-\d+\])\s*", re.I)
_USER = re.compile(r"^\s*(el )?usuario\s+", re.IGNORECASE)
_USER_INFINITIVE = re.compile(
    r"^\s*(el usuario\s+)?[a-záéíóúñ]+(ar|er|ir)\b",
    re.IGNORECASE,
)
_STATE_LEAD = re.compile(
    r"^\s*(el usuario\s+)?(est[aá]|se encuentra|tiene|cuenta con|desbloque[oó]|se muestra)\b",
    re.IGNORECASE,
)
_NOT_A_STEP = re.compile(
    r"^\s*(asegurar que|validaci[oó]n de|crear pantalla|rule\s*:|el espacio donde|"
    r"no se logra|la llave se encuentra|pantalla de)\b",
    re.IGNORECASE,
)
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
_NEGATIVE = re.compile(r"inv[aá]lid|error|mensaje|rechaz|no se (muestra|permite)|incorrect|no es v[aá]lido", re.I)
_SUCCESS = re.compile(r"\b(éxito|exito|correctamente|permite|se muestra el (comprobante|resultado)|confirma)\b", re.I)
_TECH_RESULT = re.compile(
    r"https?://|/services/|/v\d+/|\b(GET|POST|PUT|PATCH|DELETE)\b|\bHTTP\b|"
    r"\bstatus codes?\b|status code|\"\d{3}\"|"
    r"`[^`]+`|"
    r"\b[A-Za-z]+_[A-Za-z0-9_]+\b|"
    r"apa/metadata|"
    r"module_version",
    re.IGNORECASE,
)
_KEY_VALUE = re.compile(r"\b[A-Za-z][A-Za-z0-9_]*:\s*(\"[^\"]+\"|[^\s;]+)")
_ADF_NOISE = re.compile(r"\b(id-\d+|smartlink|mention)\b", re.IGNORECASE)
_ENDPOINT = re.compile(r"https?://|/v\d+/|\b(GET|POST|PUT|PATCH|DELETE|HTTP)\b|status code", re.I)
_PIPE_TABLE = re.compile(r"\|[^|\n]+\|")
_QUOTED = re.compile(r'["\u201c]([^"\u201d\n]{2,80})["\u201d]')
_STOP = {
    "el", "la", "los", "las", "un", "una", "de", "del", "en", "al", "se", "que",
    "con", "por", "para", "cuando", "usuario", "then", "when", "given", "and",
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
    out = _FEATURE.sub("", out).strip(" :-")
    out = _FLOW_MARK.sub(" ", out)
    return re.sub(r"\s+", " ", out).strip()[:120]


def is_tester_action(action: str | None) -> bool:
    raw = (action or "").strip()
    if not raw or _GENERIC.match(raw) or _NOT_A_STEP.match(raw) or _STATE_LEAD.match(raw):
        return False
    return bool(_USER_INFINITIVE.match(raw))


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
        if text and is_tester_action(text):
            return text
    if unit.user_action:
        text = to_infinitive(unit.user_action)
        if text and is_tester_action(text):
            return text
    return ""


def polish_expected(text: str | None, *, title: str | None = None) -> str:
    raw = rewrite_expected(text or "", title)
    raw = re.sub(
        r"el (servicio|sistema|backend|frontend) (responde|consulta|solicita)[^\n.;]*?( y )?",
        "",
        raw,
        flags=re.I,
    )
    raw = re.sub(r"se ejecuta el API[^\n.;]*", " ", raw, flags=re.I)
    raw = re.sub(r"se obtiene un(a respuesta)?[^\n.;]*status code[^\n.;]*", " ", raw, flags=re.I)
    raw = re.sub(r'se debe realizar una nueva llamada al servicio[^\n.;]*', " ", raw, flags=re.I)
    raw = re.sub(r'"/[^"]+"', " ", raw)
    raw = re.sub(r"status code[^\n.;]*", " ", raw, flags=re.I)
    raw = re.sub(r'"\d{3}"', " ", raw)
    raw = _PIPE_TABLE.sub(" ", raw)
    chunks: list[str] = []
    for part in re.split(r"\s*;\s*", raw):
        part = part.strip(" .;")
        if not part:
            continue
        key_val = _KEY_VALUE.search(part)
        if key_val and re.search(r"[A-Za-z]+_[A-Za-z0-9_]*\s*:", part):
            value = key_val.group(1).strip().strip('"')
            part = f'"{value}"' if value else ""
        part = _TECH_RESULT.sub(" ", part)
        part = _FLOW_MARK.sub(" ", part)
        if title and _norm(part) == _norm(title):
            continue
        part = re.sub(r"\s+", " ", part).strip(" :;")
        if part:
            chunks.append(part)
    visible = "; ".join(dict.fromkeys(chunks))
    quotes = _QUOTED.findall(text or "")
    for quote in quotes:
        if quote.lower() not in visible.lower() and not re.search(r"[/_{}\[\]]", quote):
            visible = f'{visible} "{quote}"'.strip() if visible else f'"{quote}"'
    return visible


def _unit_expected(unit: CoverageUnit) -> str:
    parsed = _clauses(unit)
    parts = [item for item in (parsed.get("expected") or []) if item.strip()]
    return polish_expected("; ".join(dict.fromkeys(parts)) or unit.scenario)


def _unit_given(unit: CoverageUnit) -> str:
    parsed = _clauses(unit)
    return "; ".join(parsed.get("given") or [])


def _follows(previous: CoverageUnit, nxt: CoverageUnit) -> bool:
    """B follows A only when Given(B) describes the action or the Then of A."""
    if (previous.story_key or "") != (nxt.story_key or ""):
        return False
    given = _unit_given(nxt)
    if not given:
        return False
    return any(
        phrases_similar(given, seed)
        for seed in (_unit_action(previous), _unit_expected(previous), previous.user_action)
        if seed
    )


def _exclusive_precondition(left: CoverageUnit, right: CoverageUnit) -> bool:
    a, b = _norm(_unit_given(left) or left.normal_precondition), _norm(
        _unit_given(right) or right.normal_precondition
    )
    if not a or not b or a == b:
        return False
    return (" no " in f" {a} ") != (" no " in f" {b} ") or (("sin " in a) != ("sin " in b))


def _recoverable(previous: CoverageUnit, nxt: CoverageUnit) -> bool:
    return bool(_NEGATIVE.search(_unit_expected(previous) or "")) and bool(
        _SUCCESS.search(_unit_expected(nxt) or "")
    )


def _same_expected(left: CoverageUnit, right: CoverageUnit) -> bool:
    return _norm(_unit_expected(left)) == _norm(_unit_expected(right)) and bool(_norm(_unit_expected(left)))


def _intent_verb(unit: CoverageUnit) -> str:
    action = to_infinitive(_unit_action(unit) or unit.user_action or "")
    return (action.split() or [""])[0].lower()


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
        given = _norm(_unit_given(unit) or unit.normal_precondition)
        if groups:
            last = groups[-1][0]
            if action and action == _norm(_unit_action(last)) and given == _norm(
                _unit_given(last) or last.normal_precondition
            ):
                groups[-1].append(unit)
                continue
        groups.append([unit])
    return groups


def _surface_from_units(units: list[CoverageUnit]) -> str | None:
    blob = " ".join(f"{unit.body or ''} {unit.scenario or ''}" for unit in units)
    quoted = _QUOTED.findall(blob)
    for quote in quoted:
        if re.search(r"[/_{}\[\]]", quote):
            continue
        if " " in quote or len(quote) > 4:
            return quote
    match = re.search(r"se muestra (?:la |el |los |las )?([^\n.;]{6,60})", blob, re.I)
    if match:
        return match.group(1).strip()
    match = re.search(
        r"\b(la tarjeta|el panel|la pantalla|la sección|la home|el modal)([^\n.;]{0,40})",
        blob,
        re.I,
    )
    if match:
        return (match.group(1) + match.group(2)).strip()
    match = re.search(
        r"\b(home|banner|modal|panel|men[uú]|detalle|resumen|listado|ficha)\b",
        blob,
        re.I,
    )
    if match:
        return match.group(0)
    return None


def _split_exclusive_expected(expected: str) -> tuple[str | None, str]:
    parts = [part.strip() for part in re.split(r"\s*;\s*", expected or "") if part.strip()]
    if len(parts) < 2:
        return None, expected
    neg = [part for part in parts if _NEGATIVE.search(part)]
    pos = [part for part in parts if part not in neg]
    if neg and pos:
        return "; ".join(neg), "; ".join(pos)
    return None, expected


def _clean_test_data(parts: list[str]) -> str | None:
    data: list[str] = []
    for raw in parts:
        text = re.sub(r"\s+", " ", (raw or "").strip())
        if not text:
            continue
        text = _ADF_NOISE.sub(" ", text)
        text = re.sub(r"\s+", " ", text).strip(" ;")
        if not text:
            continue
        data.append(text)
    return "; ".join(dict.fromkeys(data)) or None


def _draft_title(units: list[CoverageUnit]) -> str:
    intent = _intent_verb(units[0])
    quotes = [
        quote
        for unit in units
        for quote in _QUOTED.findall(f"{unit.body or ''} {unit.scenario or ''} {_unit_action(unit)}")
        if not re.search(r"[/_{}\[\]]", quote)
    ]
    visible = polish_expected(_unit_expected(units[-1]) or units[-1].scenario)
    visible = re.sub(r'^se (muestra|visualiza)\s+', "", visible, flags=re.I)
    visible = visible.split(";")[0].strip(' ."')[:70]
    action_rest = " ".join(to_infinitive(_unit_action(units[0])).split()[1:]).strip()
    if quotes:
        title = f"{intent.capitalize() if intent else 'Usar'} \"{quotes[0]}\"".strip()
        if visible and _norm(quotes[0]) not in _norm(visible):
            title = f"{title} {visible}".strip()
    elif intent:
        parts = [intent.capitalize()]
        if action_rest and _norm(action_rest) not in _norm(visible):
            parts.append(action_rest)
        if visible:
            parts.append(visible)
        title = " ".join(parts).strip()
    else:
        title = visible or strip_title_prefix(units[-1].behavior)
    title = strip_title_prefix(title)
    if _norm(title) == _norm(_unit_expected(units[-1])):
        rest = to_infinitive(_unit_action(units[0]))
        title = rest[:120] if rest else (intent.capitalize() if intent else title)
    return title[:120]


def _precondition_parts(units: list[CoverageUnit], step_actions: list[str]) -> str | None:
    parts: list[str] = []
    for unit in units:
        for clause in re.split(r"\s*;\s*", _unit_given(unit) or ""):
            clause = clause.strip()
            if not clause or _FEATURE.search(clause):
                continue
            if is_user_action(clause) or any(phrases_similar(clause, action) for action in step_actions):
                continue
            parts.append(clause)
        for clause in re.split(r"\s*;\s*", unit.normal_precondition or ""):
            clause = clause.strip()
            if not clause or _FEATURE.search(clause):
                continue
            parts.append(clause)
    return normalize_precondition("; ".join(parts))


def _draft_from_units(units: list[CoverageUnit], story_units: list[CoverageUnit] | None = None) -> FlowDraft:
    story = units[0].story_key or units[0].jira_key or ""
    epic = units[0].artifact_key or units[0].rn_key or ""
    groups = _group_same_when(units)
    steps: list[CandidateStep] = []
    pending = None
    extras: list[str] = []
    first = units[0]
    first_given = _unit_given(first)
    for clause in [part.strip() for part in (first_given or "").split(";") if part.strip()]:
        if is_user_action(clause) and not phrases_similar(clause, _unit_action(first)):
            steps.append(
                CandidateStep(
                    step_number=1,
                    action=to_infinitive(clause),
                    expected_result=polish_expected(_unit_expected(first)),
                    covered_unit_ids=[first.coverage_id],
                )
            )
            break
    last_action_index = len(steps) - 1
    for group in groups:
        action = _unit_action(group[0])
        expected = polish_expected(
            "; ".join(dict.fromkeys(_unit_expected(item) for item in group if _unit_expected(item)))
        )
        covers = [item.coverage_id for item in group]
        extras.extend(item.extra_test_data or "" for item in group)
        extras.extend(note for item in group for note in (item.technical_notes or []))
        extras.extend(
            clause
            for item in group
            for clause in (_clauses(item).get("technical") or [])
        )
        extras.extend(
            hit
            for item in group
            for hit in re.findall(
                r"\b(?:GET|POST|PUT|PATCH|DELETE)\b(?:\s+\S+)?|/services/\S+|module_version\S*",
                item.body or "",
                flags=re.I,
            )
        )
        quoted = [
            quote
            for item in group
            for quote in _QUOTED.findall(item.body or "")
            if not re.search(r"[/_{}\[\]]", quote)
        ]
        if action and quoted and quoted[0] not in action:
            action = f'{action} "{quoted[0]}"'
        if not action:
            if last_action_index >= 0:
                prev = steps[last_action_index]
                prev.expected_result = polish_expected(
                    "; ".join(part for part in (prev.expected_result, expected) if part)
                )
                prev.covered_unit_ids = list(dict.fromkeys([*(prev.covered_unit_ids or []), *covers]))
                continue
            surface = _surface_from_units(story_units or units)
            if surface:
                action = f'Abrir "{surface}"' if " " in surface or len(surface) < 40 else f"Abrir {surface}"
            else:
                pending = "sin acción de usuario soportable en las unidades cubiertas"
                continue
        neg, pos = _split_exclusive_expected(expected)
        if neg and pos:
            steps.append(
                CandidateStep(
                    step_number=len(steps) + 1,
                    action=f"{action} con un dato inválido",
                    expected_result=neg,
                    covered_unit_ids=covers,
                )
            )
            steps.append(
                CandidateStep(
                    step_number=len(steps) + 1,
                    action=f"{action} con el dato válido",
                    expected_result=pos,
                    covered_unit_ids=covers,
                )
            )
            last_action_index = len(steps) - 1
            continue
        steps.append(
            CandidateStep(
                step_number=len(steps) + 1,
                action=action,
                expected_result=expected or polish_expected(group[0].scenario),
                covered_unit_ids=covers,
            )
        )
        last_action_index = len(steps) - 1
    if not steps and pending:
        steps.append(
            CandidateStep(
                step_number=1,
                action="",
                expected_result=polish_expected(_unit_expected(units[0])),
                covered_unit_ids=[unit.coverage_id for unit in units],
            )
        )
    for index, step in enumerate(steps, start=1):
        step.step_number = index
        step.expected_result = polish_expected(step.expected_result)
    cleaned = _clean_test_data(extras)
    if cleaned and steps:
        steps[0].test_data = cleaned
    return FlowDraft(
        story_key=story,
        epic_key=epic,
        units=units,
        title=_draft_title(units),
        precondition=_precondition_parts(units, [step.action for step in steps]),
        steps=steps,
        test_data=cleaned,
        pending_reason=pending,
        evidence=" | ".join(dict.fromkeys((unit.evidence or "").split("\n", 1)[0] for unit in units))[:2000],
        applied_rules=["composed-flow"],
    )


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
        if _recoverable(prev, nxt) or _follows(prev, nxt):
            segments[-1].append(nxt)
            continue
        same_when = _norm(_unit_action(prev)) == _norm(_unit_action(nxt)) and bool(_norm(_unit_action(prev)))
        same_given = _norm(_unit_given(prev) or prev.normal_precondition) == _norm(
            _unit_given(nxt) or nxt.normal_precondition
        )
        if same_when and same_given and (_same_expected(prev, nxt) or not (_unit_expected(prev) and _unit_expected(nxt))):
            segments[-1].append(nxt)
            continue
        prev_intent, next_intent = _intent_verb(prev), _intent_verb(nxt)
        if prev_intent and next_intent and prev_intent != next_intent:
            segments.append([nxt])
            continue
        if _same_expected(prev, nxt) and prev_intent != next_intent:
            segments.append([nxt])
            continue
        segments.append([nxt])
    return [_draft_from_units(segment, story_units=ordered) for segment in segments]


def draft_to_candidate(
    draft: FlowDraft,
    existing: list[dict[str, str]],
    duplicate_of,
) -> GeneratedCaseCandidate:
    covers = [unit.coverage_id for unit in draft.units]
    rules = list(draft.applied_rules)
    if draft.pending_reason:
        rules.append(f"pendiente-qc:{draft.pending_reason}")
    applicability = "na_ambiente" if draft.units and all(
        (unit.applicability or "ejecutable") == "na_ambiente" for unit in draft.units
    ) else "ejecutable"
    return GeneratedCaseCandidate(
        name=draft.title[:120],
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
        review_required=True,
        covers=covers,
        covered_unit_ids=covers,
        applicability=applicability,
        applicability_reason=(
            draft.units[0].applicability_reason if applicability == "na_ambiente" else draft.pending_reason
        ),
        applied_rules=rules,
        generation_origin="composed-flow",
        source_type="functionality",
        confidence="medium" if draft.pending_reason else "high",
        requires_condition=any(bool(unit.requires_condition) for unit in draft.units),
    )


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
    seen_na: dict[str, GeneratedCaseCandidate] = {}
    for unit in na_units:
        fingerprint = _norm(f"{unit.scenario} {_unit_expected(unit)}")
        if fingerprint in seen_na:
            current = seen_na[fingerprint]
            stories = list(dict.fromkeys(
                [*(current.related_jira or "").split(" | "), unit.story_key or unit.jira_key or ""]
            ))
            current.related_jira = " | ".join(part for part in stories if part)
            current.covers = list(dict.fromkeys([*(current.covers or []), unit.coverage_id]))
            current.covered_unit_ids = list(current.covers)
            continue
        draft = _draft_from_units([unit], story_units=[unit])
        candidate = draft_to_candidate(draft, existing, duplicate_of)
        candidate.applicability = "na_ambiente"
        seen_na[fingerprint] = candidate
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


def candidate_violates_writing_standard(candidate: GeneratedCaseCandidate) -> bool:
    if len(candidate.name or "") > 150:
        return True
    if _ADF_NOISE.search(candidate.test_data or ""):
        return True
    for step in candidate.steps:
        if step.action and not is_tester_action(step.action):
            return True
        if _TECH_RESULT.search(step.expected_result or ""):
            return True
        if _norm(step.expected_result) == _norm(candidate.name):
            return True
    return False


def validate_composed_candidates(
    candidates: list[GeneratedCaseCandidate],
    inventory: list[CoverageUnit],
    *,
    fill_missing,
) -> list[GeneratedCaseCandidate]:
    by_id = {unit.coverage_id: unit for unit in inventory}
    executable_ids = {
        unit.coverage_id
        for unit in inventory
        if (unit.applicability or "ejecutable") != "na_ambiente"
    }
    repaired: list[GeneratedCaseCandidate] = []
    covered: set[str] = set()
    rejected: list[CoverageUnit] = []
    for candidate in candidates:
        stories = {
            ((by_id.get(cid).story_key if by_id.get(cid) else None) or "")
            for cid in (candidate.covers or candidate.covered_unit_ids or [])
        }
        stories.discard("")
        if len(stories) > 1:
            ids = [cid for cid in (candidate.covers or []) if cid in by_id]
            rejected.extend(by_id[cid] for cid in ids)
            continue
        candidate.name = strip_title_prefix(candidate.name)[:120]
        new_steps: list[CandidateStep] = []
        for step in candidate.steps:
            ids = list(step.covered_unit_ids or candidate.covers or [])
            units = [by_id[cid] for cid in ids if cid in by_id]
            action = to_infinitive(step.action)
            if units and (not is_tester_action(action)):
                action = _unit_action(units[0])
            expected = polish_expected(step.expected_result, title=candidate.name)
            if units:
                source = _unit_expected(units[0])
                if expected and source and not phrases_similar(expected, source) and not _QUOTED.search(expected):
                    expected = source
                step.covered_unit_ids = [unit.coverage_id for unit in units]
                covered.update(step.covered_unit_ids)
            if not is_tester_action(action):
                candidate.applied_rules = list(
                    dict.fromkeys(
                        [*(candidate.applied_rules or []), "pendiente-qc:sin acción de usuario soportable"]
                    )
                )
                candidate.review_required = True
            step.action = action
            step.expected_result = expected
            if action or expected:
                new_steps.append(step)
        candidate.steps = new_steps
        for index, step in enumerate(candidate.steps, start=1):
            step.step_number = index
        ids = list(dict.fromkeys([*(candidate.covers or []), *(candidate.covered_unit_ids or [])]))
        for step in candidate.steps:
            ids.extend(step.covered_unit_ids or [])
        candidate.covers = list(dict.fromkeys(ids))
        candidate.covered_unit_ids = list(candidate.covers)
        covered.update(candidate.covers)
        if candidate.generation_origin == "llm" and candidate_violates_writing_standard(candidate):
            rejected.extend(by_id[cid] for cid in candidate.covers if cid in by_id)
            continue
        na_ids = [cid for cid in candidate.covers if cid in by_id and by_id[cid].applicability == "na_ambiente"]
        exe_ids = [cid for cid in candidate.covers if cid in by_id and (by_id[cid].applicability or "ejecutable") != "na_ambiente"]
        if na_ids and exe_ids:
            candidate.covers = exe_ids
            candidate.covered_unit_ids = exe_ids
            candidate.applicability = "ejecutable"
        elif na_ids and not exe_ids:
            candidate.applicability = "na_ambiente"
        elif not candidate.applicability:
            candidate.applicability = "ejecutable"
        repaired.append(candidate)
    missing = [unit for unit in inventory if unit.coverage_id in executable_ids and unit.coverage_id not in covered]
    missing.extend(unit for unit in rejected if unit.coverage_id not in covered)
    if missing and fill_missing is not None:
        extra = fill_missing(list({unit.coverage_id: unit for unit in missing}.values()))
        for row in extra:
            if not row.generation_origin or row.generation_origin == "composed-flow":
                row.generation_origin = "coverage-fill"
        repaired.extend(extra)
    return repaired
