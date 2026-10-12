"""One Test Case per Jira Scenario (FASE 7). Flow composition stays in case_composer."""

from __future__ import annotations

import re

from app.config import settings
from app.schemas.case_generation import CandidateStep, CoverageUnit, GeneratedCaseCandidate, GenerationStats
from app.services.case_composer import (
    FlowDraft,
    _TECH_RESULT,
    _ENDPOINT,
    _QUOTED,
    _STATE_LEAD,
    candidate_violates_writing_standard,
    draft_to_candidate,
    is_tester_action,
    polish_expected,
    strip_title_prefix,
    to_infinitive,
    _unit_expected,
)
from app.services.coverage_quality import normalize_precondition
from app.services.executability import is_user_action
from app.services.gherkin_coverage import TECH_VERIFY_MARK

_EVENT_THEN = re.compile(
    r"\b(se env[ií]a|se registra|se dispara|se reporta|se llama).{0,60}\b(evento|m[eé]trica|servicio|api|endpoint)\b",
    re.I,
)


def composition_mode() -> str:
    raw = (getattr(settings, "case_composition_mode", None) or "scenario").strip().lower()
    return raw if raw in {"scenario", "flow"} else "scenario"


def scenario_group_key(unit: CoverageUnit) -> str:
    if (unit.outline_strategy or "single") in {"split_functional", "group"}:
        base = re.sub(r"\s*\([^)]*\)\s*$", "", unit.scenario or "").strip()
        obs = re.sub(r"\W+", " ", " ".join(unit.observable_then or []).lower()).strip()
        return f"{unit.story_key or unit.jira_key}|{base}|{unit.outline_strategy}|{obs}"
    return (unit.scenario_group or "").strip() or (
        f"{unit.story_key or unit.jira_key}|{unit.scenario}|{unit.technical_group or ''}|{unit.outline_strategy}"
    )


def _walk_gwt(body: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    kind = "given"
    for raw in (body or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if re.match(r"^\s*(Given|Dado que|Dado)\b", line, re.I):
            kind = "given"
            line = re.sub(r"^\s*(Given|Dado que|Dado)\s+", "", line, flags=re.I)
        elif re.match(r"^\s*(When|Cuando)\b", line, re.I):
            kind = "when"
            line = re.sub(r"^\s*(When|Cuando)\s+", "", line, flags=re.I)
        elif re.match(r"^\s*(Then|Entonces)\b", line, re.I):
            kind = "then"
            line = re.sub(r"^\s*(Then|Entonces)\s+", "", line, flags=re.I)
        elif re.match(r"^\s*(And|Y|But|Pero)\b", line, re.I):
            line = re.sub(r"^\s*(And|Y|But|Pero)\s+", "", line, flags=re.I)
        elif line.startswith("|"):
            rows.append(("table", line))
            continue
        else:
            continue
        if line:
            rows.append((kind, line.strip()))
    return rows


def _table_as_list(lines: list[str]) -> str:
    rows: list[list[str]] = []
    for line in lines:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells:
            rows.append(cells)
    if len(rows) < 2:
        return ""
    headers = rows[0]
    parts: list[str] = []
    for row in rows[1:]:
        bits = []
        for index, header in enumerate(headers):
            value = row[index] if index < len(row) else ""
            if not value:
                continue
            bits.append(f'{header} "{value}"' if " " in value or len(value) > 3 else f"{header} {value}")
        if bits:
            parts.append(", ".join(bits))
    return "; ".join(parts)


def _nav_action(clause: str) -> str:
    inf = to_infinitive(clause)
    quoted = _QUOTED.search(clause or "")
    if quoted and re.search(r"(da clic|hace clic|seleccion|presion)", clause, re.I):
        return f'Seleccionar "{quoted.group(1)}"'
    if re.search(
        r"^\s*(el usuario\s+)?(visualiza|ve)\s+(la |el )?(pantalla|home|modal|panel|men[uú])",
        clause,
        re.I,
    ):
        rest = re.sub(r"^\s*(el usuario\s+)?(visualiza|ve)\s+", "", clause, flags=re.I).strip()
        return f"Abrir {rest}".strip()
    if is_tester_action(inf):
        return inf
    if is_user_action(clause) and not _STATE_LEAD.match(inf):
        return inf
    return ""


def _variant_table(units: list[CoverageUnit], walked: list[tuple[str, str]]) -> str | None:
    lines: list[str] = []
    table_buf: list[str] = []
    for kind, text in walked:
        if kind == "table":
            table_buf.append(text)
            continue
        if table_buf:
            listed = _table_as_list(table_buf)
            table_buf.clear()
            if listed:
                for part in listed.split("; "):
                    if ":" in part:
                        left, right = part.split(":", 1)
                        lines.append(f"{left.strip()} | {right.strip()}")
                    else:
                        lines.append(f"{part} | {_unit_expected(units[0]) or ''}")
    if table_buf:
        listed = _table_as_list(table_buf)
        if listed:
            for part in listed.split("; "):
                if ":" in part:
                    left, right = part.split(":", 1)
                    lines.append(f"{left.strip()} | {right.strip()}")
    expected = _unit_expected(units[0]) or ""
    for unit in units:
        for chunk in re.split(r";\s*", unit.extra_test_data or ""):
            chunk = chunk.strip()
            chunk = re.sub(r"^Variantes técnicas[^:]+:\s*", "", chunk)
            chunk = re.sub(r"^Example funcional explícito:\s*", "", chunk)
            if not chunk or "=" not in chunk:
                continue
            left, right = chunk.split("=", 1)
            if re.search(r"https?://|/services/|\b(GET|POST|PUT|PATCH|DELETE|HTTP)\b", chunk, re.I):
                continue
            lines.append(f"{left.strip()} | {right.strip() or expected}")
    unique = list(dict.fromkeys(line for line in lines if line.strip(" |")))
    if len(unique) < 2:
        return None
    return "Condición | Resultado esperado\n" + "\n".join(unique)


def _examples_as_data(units: list[CoverageUnit]) -> str | None:
    parts: list[str] = []
    for unit in units:
        raw = unit.extra_test_data or ""
        for chunk in re.split(r";\s*", raw):
            chunk = chunk.strip()
            if not chunk:
                continue
            if re.search(r"https?://|/services/|\b(GET|POST|PUT|PATCH|DELETE|HTTP)\b", chunk, re.I):
                continue
            chunk = re.sub(r"^Variantes técnicas[^:]+:\s*", "", chunk)
            chunk = re.sub(r"^Example funcional explícito:\s*", "", chunk)
            chunk = re.sub(r"^Códigos HTTP[^:]+:\s*", "", chunk)
            if chunk:
                parts.append(chunk)
    return "; ".join(dict.fromkeys(parts)) or None


def compose_scenario_units(units: list[CoverageUnit]) -> FlowDraft:
    primary = units[0]
    evidence_body = (primary.evidence or "").split("\n", 1)
    body = evidence_body[1] if len(evidence_body) > 1 else (primary.body or "")
    walked = _walk_gwt(body)
    pre: list[str] = []
    tech: list[str] = []
    nav: list[str] = []
    for unit in units:
        for clause in re.split(r"\s*;\s*", unit.normal_precondition or ""):
            clause = clause.strip()
            if not clause:
                continue
            action = _nav_action(clause)
            if action:
                nav.append(action)
            elif _TECH_RESULT.search(clause) or _ENDPOINT.search(clause):
                tech.append(clause)
            else:
                pre.append(clause)
    pending = None
    steps: list[CandidateStep] = []
    pending_then: list[str] = []
    table_buf: list[str] = []
    covers = [unit.coverage_id for unit in units]
    system_when = False

    def _flush_table() -> str:
        text = _table_as_list(table_buf)
        table_buf.clear()
        return text

    def _attach_then(text: str) -> None:
        if _TECH_RESULT.search(text or "") or _ENDPOINT.search(text or "") or _EVENT_THEN.search(text or ""):
            tech.append(text)
            if TECH_VERIFY_MARK not in tech:
                tech.append(TECH_VERIFY_MARK)
            return
        cleaned = polish_expected(text)
        if not cleaned:
            return
        if steps:
            prev = steps[-1]
            prev.expected_result = polish_expected(
                "; ".join(part for part in (prev.expected_result, cleaned) if part)
            )
        else:
            pending_then.append(cleaned)

    for kind, text in walked:
        if kind == "table":
            table_buf.append(text)
            continue
        if table_buf:
            listed = _flush_table()
            if listed:
                _attach_then(listed)
        for match in _TECH_RESULT.finditer(text):
            tech.append(match.group(0))
        if kind == "given":
            action = _nav_action(text)
            if action:
                nav.append(action)
            elif not (_TECH_RESULT.search(text) or _ENDPOINT.search(text)):
                pre.append(text)
            continue
        if kind == "when":
            action = to_infinitive(text)
            if not is_tester_action(action) and not is_user_action(text):
                tech.append(text)
                system_when = True  # noqa: F841 - used after the walk
                continue
            if not is_tester_action(action):
                continue
            expected = polish_expected("; ".join(pending_then)) if pending_then else ""
            pending_then = []
            steps.append(
                CandidateStep(
                    step_number=len(steps) + 1,
                    action=action,
                    expected_result=expected,
                    covered_unit_ids=list(covers),
                )
            )
            continue
        if kind == "then":
            _attach_then(text)
    if table_buf:
        listed = _flush_table()
        if listed:
            _attach_then(listed)
    for action in reversed(list(dict.fromkeys(nav))):
        if any(action.lower() == (step.action or "").lower() for step in steps):
            continue
        steps.insert(
            0,
            CandidateStep(step_number=1, action=action, expected_result="", covered_unit_ids=list(covers)),
        )
    merged_expected = polish_expected(
        "; ".join(dict.fromkeys(item for unit in units for item in (_unit_expected(unit),) if item))
    )
    if steps and not steps[-1].expected_result and merged_expected:
        steps[-1].expected_result = merged_expected
    if pending_then and steps:
        _attach_then("; ".join(pending_then))
    if not any(is_tester_action(step.action) for step in steps):
        for unit in units:
            fallback = _nav_action(unit.user_action or "") or to_infinitive(unit.user_action or "")
            if is_tester_action(fallback) or is_user_action(unit.user_action or ""):
                visible = merged_expected or polish_expected("; ".join(pending_then))
                if not visible and any("regresion-funcional" in (unit.applied_rules or []) for unit in units):
                    visible = polish_expected(primary.story_summary or primary.scenario)
                steps.append(
                    CandidateStep(
                        step_number=1,
                        action=fallback,
                        expected_result=visible,
                        covered_unit_ids=list(covers),
                    )
                )
                break
    if not any(is_tester_action(step.action) for step in steps) and (system_when or nav):
        for action in list(dict.fromkeys(nav))[:1]:
            steps.append(
                CandidateStep(
                    step_number=1,
                    action=action,
                    expected_result=merged_expected or polish_expected("; ".join(pending_then)),
                    covered_unit_ids=list(covers),
                )
            )
            break
    if not any(is_tester_action(step.action) for step in steps):
        pending = "sin acción de usuario en Jira"
        if any("verificacion-tecnica" in (unit.applied_rules or []) for unit in units):
            pending = "verificación técnica"
        steps = []
    for index, step in enumerate(steps, start=1):
        step.step_number = index
        step.expected_result = polish_expected(step.expected_result)
    title = strip_title_prefix(primary.scenario)[:120]
    tech_notes = list(
        dict.fromkeys([*tech, *(note for unit in units for note in (unit.technical_notes or []))])
    )
    return FlowDraft(
        story_key=primary.story_key or primary.jira_key or "",
        epic_key=primary.artifact_key or primary.rn_key or "",
        units=units,
        title=title,
        precondition=normalize_precondition("; ".join(dict.fromkeys(pre))),
        steps=steps,
        test_data=_examples_as_data(units),
        pending_reason=pending,
        evidence=primary.evidence or title,
        applied_rules=["scenario-case", *{
            rule
            for unit in units
            for rule in (unit.applied_rules or [])
            if rule in {"verificacion-tecnica", "regresion-funcional", "na-ambiente"}
            or str(rule).startswith("pendiente-qc")
        }],
        technical_reference="; ".join(tech_notes) or None,
    )


def compose_scenario_inventory(
    inventory: list[CoverageUnit],
    existing: list[dict[str, str]],
    duplicate_of,
) -> list[GeneratedCaseCandidate]:
    groups: dict[str, list[CoverageUnit]] = {}
    order: list[str] = []
    for unit in inventory:
        key = scenario_group_key(unit)
        if key not in groups:
            order.append(key)
        groups.setdefault(key, []).append(unit)
    out: list[GeneratedCaseCandidate] = []
    for key in order:
        draft = compose_scenario_units(groups[key])
        candidate = draft_to_candidate(draft, existing, duplicate_of)
        candidate.generation_origin = "scenario-case"
        candidate.justification = "Caso 1:1 con escenario de Jira."
        candidate.use_case_title = groups[key][0].story_summary
        if draft.technical_reference:
            candidate.technical_reference = draft.technical_reference
        candidate.variant_table = _variant_table(groups[key], _walk_gwt(groups[key][0].body or ""))
        candidate.applied_rules = list(dict.fromkeys([*(candidate.applied_rules or []), *(draft.applied_rules or [])]))
        out.append(candidate)
    return contextualize_duplicate_titles(out)


def feature_context(candidate: GeneratedCaseCandidate) -> str:
    raw = (candidate.use_case_title or candidate.description or "").strip()
    raw = re.sub(r"^\s*feature\s*:?\s*", "", raw, flags=re.I).strip(" :-")
    if re.sub(r"\W+", " ", raw.lower()).strip() == re.sub(r"\W+", " ", (candidate.name or "").lower()).strip():
        return ""
    return raw[:48]


def contextualize_duplicate_titles(candidates: list[GeneratedCaseCandidate]) -> list[GeneratedCaseCandidate]:
    grouped: dict[str, list[GeneratedCaseCandidate]] = {}
    for candidate in candidates:
        epic = (candidate.related_functionality or "").split("|")[0].strip()
        normalized = re.sub(r"\W+", " ", (candidate.name or "").lower()).strip()
        grouped.setdefault(f"{epic}|{normalized}", []).append(candidate)
    for rows in grouped.values():
        if len(rows) < 2:
            continue
        for candidate in rows:
            extra = feature_context(candidate)
            if extra and extra.lower() not in (candidate.name or "").lower():
                candidate.name = f"{strip_title_prefix(candidate.name)[:80]} — {extra}".strip()[:120]
    return candidates


def llm_rewrite_is_safe(base: GeneratedCaseCandidate, llm: GeneratedCaseCandidate) -> bool:
    if len(base.steps) != len(llm.steps):
        return False
    if set(base.covers or []) != set(llm.covers or []):
        return False
    quotes = _QUOTED.findall(
        " ".join([base.name or ""] + [f"{step.action} {step.expected_result}" for step in base.steps])
    )
    blob = " ".join([llm.name or ""] + [f"{step.action} {step.expected_result}" for step in llm.steps])
    for quote in quotes:
        if quote.lower() not in blob.lower():
            return False
    if candidate_violates_writing_standard(llm):
        return False
    return True


def align_llm_to_deterministic(
    deterministic: list[GeneratedCaseCandidate],
    llm_candidates: list[GeneratedCaseCandidate],
) -> list[GeneratedCaseCandidate]:
    by_covers: dict[tuple[str, ...], GeneratedCaseCandidate] = {}
    for row in llm_candidates:
        key = tuple(sorted(row.covers or row.covered_unit_ids or []))
        if key:
            by_covers[key] = row
    out: list[GeneratedCaseCandidate] = []
    for base in deterministic:
        key = tuple(sorted(base.covers or []))
        other = by_covers.get(key)
        if other and llm_rewrite_is_safe(base, other):
            other.technical_reference = base.technical_reference
            other.applicability = base.applicability
            other.applicability_reason = base.applicability_reason
            other.covers = list(base.covers or [])
            other.covered_unit_ids = list(base.covers or [])
            out.append(other)
        else:
            out.append(base)
    return out


def fill_scenario_ledger(
    stats: GenerationStats,
    inventory: list[CoverageUnit],
    candidates: list[GeneratedCaseCandidate],
) -> None:
    covered: dict[str, GeneratedCaseCandidate] = {}
    for candidate in candidates:
        for cid in candidate.covers or candidate.covered_unit_ids or []:
            covered[cid] = candidate
    seen: set[tuple[str, str]] = {
        (str(row.get("story") or ""), str(row.get("scenario") or "")) for row in stats.scenario_ledger
    }
    for unit in inventory:
        if (unit.source_origin or "gherkin") != "gherkin":
            continue
        scenario = re.sub(r"\s*\([^)]*\)\s*$", "", unit.scenario or "").strip()
        key = (unit.story_key or "", scenario)
        if key in seen:
            continue
        seen.add(key)
        match = covered.get(unit.coverage_id)
        rules = list(unit.applied_rules or []) + list((match.applied_rules if match else []) or [])
        case_pending = bool(
            match
            and (
                not match.steps
                or any(str(rule).startswith("pendiente-qc") for rule in (match.applied_rules or []))
            )
        )
        if (unit.applicability or "") == "na_ambiente" or (match and (match.applicability or "") == "na_ambiente"):
            estado, motivo, case_id = (
                "na_ambiente",
                (match.applicability_reason if match else None) or unit.applicability_reason or "na_ambiente",
                match.name if match else "",
            )
        elif match and match.steps and not case_pending:
            estado, motivo, case_id = "caso ejecutable", "", match.name
        elif any(str(rule) == "verificacion-tecnica" for rule in rules) and (
            match is None or not match.steps
        ):
            estado, motivo, case_id = (
                "verificación técnica",
                "Then técnico sin comportamiento visible en la historia",
                match.name if match else "",
            )
        elif match is None or case_pending:
            estado, motivo, case_id = (
                "pendiente de revisión QC",
                (match.applicability_reason if match else None) or "sin acción de usuario en Jira",
                match.name if match else "",
            )
        else:
            estado, motivo, case_id = "caso ejecutable", "", match.name if match else ""
        stats.scenario_ledger.append(
            {
                "story": unit.story_key or "",
                "epic": unit.artifact_key or "",
                "scenario": scenario,
                "estado": estado,
                "motivo": motivo,
                "case_id": case_id,
            }
        )
