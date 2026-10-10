"""Separate B (condition), A (user action) and C (observable result) in Test Cases.

Does not change A–G roles, Coverage Unit identity, covers, or case volume.
Does not invent screens. Never turns a condition into a user verb.
"""

from __future__ import annotations

import re

from app.schemas.case_generation import (
    CandidateStep,
    CoverageUnit,
    GeneratedCaseCandidate,
)
from app.services.coverage_quality import normalize_precondition

STABLE_GENERIC_STEP = "El usuario ingresa al flujo correspondiente."

_GENERIC_EXPECTED = re.compile(
    r"se muestra el comportamiento esperado|"
    r"el sistema responde correctamente|"
    r"se muestra un mensaje$|"
    r"la operaci[oó]n contin[uú]a correctamente|"
    r"el flujo funciona correctamente|"
    r"se observa el (resultado|comportamiento) (declarado|esperado)(?! para)|"
    r"observa el resultado en la interfaz|"
    r"sin condiciones no evidenciadas",
    re.IGNORECASE,
)
_FORBIDDEN_GENERIC_ACTION = re.compile(
    r"recorre la experiencia cuando|"
    r"recorre la experiencia de:|"
    r"recorre el flujo de la funcionalidad descrita|"
    r"recorre la experiencia descrita en el escenario|"
    r"contin[uú]a (el|con el) (flujo|proceso)\.?$|"
    r"realiza la acci[oó]n correspondiente|"
    r"navega al flujo correspondiente|"
    r"realiza el procedimiento indicado|"
    r"completa el flujo funcional\.?$",
    re.IGNORECASE,
)
_SMUGGLED_WHEN = re.compile(r"\bcuando\b", re.IGNORECASE)
_VALIDAR_PREFIX = re.compile(r"^\s*(validar( el comportamiento de la experiencia cuando)?)\s+", re.I)
_CUANDO_PREFIX = re.compile(r"^\s*cuando\s+", re.I)
_USER_ACTION = re.compile(
    r"^\s*(el )?usuario\b|"
    r"^\s*(selecciona|ingresa|abre|cierra|presiona|navega|visualiza|transacciona|"
    r"reproduce|busca|completa|confirma|cancela|inicia sesi[oó]n|sale de|"
    r"da clic|hace clic|elige|pulsa)",
    re.IGNORECASE,
)
_STATE_OBSERVATION = re.compile(
    r"^\s*se (muestra|presenta|visualiza|abre|oculta|mantiene|reproduce)|"
    r"^\s*(debe(n)? )?(mostrarse|visualizarse|presentarse)|"
    r"supera el l[ií]mite|"
    r"^\s*el texto informativo\b|"
    r"^\s*la (pantalla|leyenda|experiencia)\b",
    re.IGNORECASE,
)
_TECHNICAL_ACTOR = re.compile(
    r"\b(el sistema|el backend|el servicio|la aplicaci[oó]n|el handler|"
    r"el frontend|consulta|construye|procesa|obtiene|genera|invoca)\b",
    re.IGNORECASE,
)
_GIVEN = re.compile(r"^\s*(Given|Dado que|Dado)\s+", re.IGNORECASE)
_WHEN = re.compile(r"^\s*(When|Cuando)\s+", re.IGNORECASE)
_THEN = re.compile(r"^\s*(Then|Entonces)\s+", re.IGNORECASE)
_AND = re.compile(r"^\s*(And|Y|Pero|But)\s+", re.IGNORECASE)


def condition_clause(text: str | None) -> str:
    raw = re.sub(r"\s+", " ", (text or "").strip().rstrip("."))
    if not raw:
        return ""
    raw = _VALIDAR_PREFIX.sub("", raw)
    raw = _CUANDO_PREFIX.sub("", raw)
    if raw and raw[0].isupper() and (len(raw) == 1 or not raw[1].isupper()):
        raw = raw[0].lower() + raw[1:]
    return raw.strip()


def build_test_intent(scenario: str, condition: str | None = None) -> str:
    core = condition_clause(condition) or condition_clause(scenario)
    if not core:
        return ""
    if core.startswith("validar"):
        return core[0].upper() + core[1:] + ("." if not core.endswith(".") else "")
    return f"Validar el comportamiento de la experiencia cuando {core}."


def is_user_action(text: str | None) -> bool:
    bare = (text or "").strip()
    if not bare:
        return False
    if _TECHNICAL_ACTOR.search(bare) and not _USER_ACTION.search(bare):
        return False
    return bool(_USER_ACTION.search(bare))


def is_state_observation(text: str | None) -> bool:
    bare = (text or "").strip()
    if not bare or is_user_action(bare):
        return False
    return bool(_STATE_OBSERVATION.search(bare))


def is_technical_action(text: str | None) -> bool:
    bare = (text or "").strip()
    if not bare or is_user_action(bare):
        return False
    return bool(_TECHNICAL_ACTOR.search(bare))


def is_stable_generic_step(text: str | None) -> bool:
    return re.sub(r"\s+", " ", (text or "").strip().lower()) == STABLE_GENERIC_STEP.lower()


def is_generic_expected(text: str | None) -> bool:
    return bool(_GENERIC_EXPECTED.search((text or "").strip()))


def is_generic_action(text: str | None) -> bool:
    """Forbidden generic or condition smuggled into the verb. Stable generic A is allowed."""
    bare = (text or "").strip()
    if is_stable_generic_step(bare):
        return False
    return bool(_FORBIDDEN_GENERIC_ACTION.search(bare) or step_smuggles_condition(bare))


def step_smuggles_condition(text: str | None) -> bool:
    bare = (text or "").strip()
    if not bare:
        return False
    if is_stable_generic_step(bare):
        return False
    return bool(_SMUGGLED_WHEN.search(bare) or _FORBIDDEN_GENERIC_ACTION.search(bare))


def extract_smuggled_condition(text: str | None) -> str | None:
    bare = (text or "").strip().rstrip(".")
    match = re.search(r"\bcuando\s+(.+)$", bare, re.IGNORECASE)
    if not match:
        return None
    clause = condition_clause(match.group(1))
    if not clause:
        return None
    return clause[0].upper() + clause[1:] + "."


def bound_user_action(_name: str = "", original: str | None = None) -> str:
    """Stable generic A. Never appends the scenario condition to the verb."""
    if original and is_user_action(original) and not step_smuggles_condition(original):
        return original.strip()
    return STABLE_GENERIC_STEP


def bound_expected(name: str, current: str | None = None) -> str:
    if current and current.strip() and not is_generic_expected(current):
        return current.strip()
    clause = condition_clause(name)
    if clause:
        return f"Se observa el comportamiento definido para cuando {clause}."
    return (current or "").strip()


def parse_scenario_clauses(body: str) -> dict[str, list[str]]:
    """Split Gherkin body into B / A / C / technical without treating every And as Given."""
    given: list[str] = []
    actions: list[str] = []
    expected: list[str] = []
    technical: list[str] = []
    mode = "given"

    def _strip_kw(pattern: re.Pattern[str], line: str) -> str:
        return pattern.sub("", line).strip()

    def _accept(kind: str, text: str) -> None:
        if not text:
            return
        if kind == "given":
            given.append(text)
            if is_technical_action(text) and not is_user_action(text):
                technical.append(text)
        elif kind == "when":
            if (
                re.search(r"\b(GET|POST|PUT|PATCH|DELETE|HTTP)\b|/[a-z]|status\s*\d|\"\"\"|```", text, re.I)
                and not is_user_action(text)
            ):
                technical.append(text)
            elif is_user_action(text):
                actions.append(text)
            elif is_state_observation(text):
                expected.append(text)
            else:
                technical.append(text)
        else:
            text = re.sub(r"\s*\|.*$", "", text).strip(" :")
            if not text:
                return
            expected.append(text)
            if is_technical_action(text) and not is_state_observation(text) and not is_user_action(text):
                technical.append(text)

    def _format_table(rows: list[list[str]]) -> str:
        if len(rows) < 2:
            return ""
        headers = rows[0]
        chunks: list[str] = []
        for row in rows[1:]:
            if not any(cell.strip() for cell in row):
                continue
            pairs = []
            for index, header in enumerate(headers):
                value = row[index] if index < len(row) else ""
                if header and value:
                    pairs.append(f"{header}: {value}")
            if pairs:
                chunks.append("; ".join(pairs))
        return " ".join(chunks)

    lines = [raw.strip() for raw in (body or "").splitlines()]
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line or line.startswith("#"):
            index += 1
            continue
        if line.startswith("|"):
            rows: list[list[str]] = []
            while index < len(lines) and lines[index].startswith("|"):
                rows.append([cell.strip() for cell in lines[index].strip("|").split("|")])
                index += 1
            formatted = _format_table(rows)
            if not formatted:
                continue
            if mode == "then":
                if expected:
                    expected[-1] = f"{expected[-1]} {formatted}".strip()
                else:
                    expected.append(formatted)
            else:
                technical.append(formatted)
            continue
        if _GIVEN.match(line):
            mode = "given"
            _accept("given", _strip_kw(_GIVEN, line))
        elif _WHEN.match(line):
            mode = "when"
            _accept("when", _strip_kw(_WHEN, line))
        elif _THEN.match(line):
            mode = "then"
            _accept("then", _strip_kw(_THEN, line))
        elif _AND.match(line):
            _accept(mode, _strip_kw(_AND, line))
        index += 1
    return {
        "given": given,
        "actions": actions,
        "expected": expected,
        "technical": technical,
    }


def _unit_condition_blob(unit: CoverageUnit) -> str:
    return " ".join(
        part
        for part in (
            unit.test_intent,
            unit.scenario,
            unit.special_condition,
            unit.normal_precondition,
        )
        if part
    )


def _candidate_condition_blob(candidate: GeneratedCaseCandidate) -> str:
    steps = " ".join(f"{step.action} {step.expected_result}" for step in candidate.steps)
    return " ".join(
        part
        for part in (
            candidate.name,
            candidate.precondition,
            candidate.test_data,
            candidate.description,
            steps,
        )
        if part
    )


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-záéíóúñ0-9]{4,}", (text or "").lower())
        if token
        not in {
            "cuando",
            "validar",
            "comportamiento",
            "experiencia",
            "usuario",
            "recorre",
            "muestra",
            "debe",
            "deben",
            "para",
            "como",
            "este",
            "esta",
            "flujo",
            "ingresa",
            "definido",
        }
    }


def differential_missing(candidate: GeneratedCaseCandidate, units: list[CoverageUnit]) -> bool:
    if not units:
        return False
    source = _tokens(" ".join(_unit_condition_blob(unit) for unit in units))
    present = _tokens(
        " ".join(
            part
            for part in (candidate.precondition, candidate.test_data, candidate.name)
            if part
        )
    )
    if not source:
        return False
    overlap = source & present
    return len(overlap) < max(1, min(3, len(source) // 4))


def expected_hides_observation(candidate: GeneratedCaseCandidate) -> bool:
    if not candidate.steps:
        return True
    return all(is_generic_expected(step.expected_result) for step in candidate.steps)


def step_needs_bac_fix(candidate: GeneratedCaseCandidate) -> bool:
    name = condition_clause(candidate.name)
    for step in candidate.steps or []:
        action = step.action or ""
        if step_smuggles_condition(action):
            return True
        if name and name in action.lower() and is_user_action(action) is False:
            return True
        if is_state_observation(action) and not is_user_action(action):
            return True
        if _FORBIDDEN_GENERIC_ACTION.search(action):
            return True
    return False


def _action_from_unit(unit: CoverageUnit) -> str:
    parsed = parse_scenario_clauses(unit.body or "")
    if parsed["actions"]:
        joined = " y ".join(dict.fromkeys(item.strip() for item in parsed["actions"] if item.strip()))
        if joined:
            return joined[0].upper() + joined[1:]
    if unit.user_action and is_user_action(unit.user_action):
        action = unit.user_action.strip()
        return action[0].upper() + action[1:]
    return STABLE_GENERIC_STEP


def _expected_from_unit(unit: CoverageUnit, name: str) -> str:
    for clause in unit.observable_then or []:
        if clause.strip() and not is_generic_expected(clause):
            return clause.strip()
    parsed = parse_scenario_clauses(unit.body or "")
    if parsed["expected"]:
        return parsed["expected"][0]
    return bound_expected(name or unit.scenario or unit.behavior)


def _given_from_unit(unit: CoverageUnit) -> str | None:
    parsed = parse_scenario_clauses(unit.body or "")
    if parsed["given"]:
        return "; ".join(dict.fromkeys(parsed["given"]))
    return unit.normal_precondition or unit.special_condition or None


_CONDITIONISH = re.compile(
    r"vac[ií]a|no se logra|no disponible|deshabilit|null|expirad|"
    r"sin (cuenta|contenido|permiso)|no (es )?posible|flag|"
    r"no est[aá] (disponible|en)|llave requerida",
    re.IGNORECASE,
)


def _title_as_condition(text: str | None) -> str | None:
    clause = condition_clause(text)
    if not clause or not _CONDITIONISH.search(clause):
        return None
    prepared = clause[0].upper() + clause[1:]
    return prepared + ("." if not prepared.endswith(".") else "")


def reconstruct_from_units(
    candidate: GeneratedCaseCandidate,
    units: list[CoverageUnit],
) -> GeneratedCaseCandidate:
    primary = units[0]
    name = candidate.name or primary.scenario
    given = _given_from_unit(primary)
    if not given:
        given = _title_as_condition(primary.scenario) or _title_as_condition(name)
    if given and given not in (candidate.precondition or ""):
        candidate.precondition = "; ".join(
            part for part in (given, candidate.precondition) if part
        )
    elif not candidate.precondition:
        candidate.precondition = given
    notes = [
        part
        for part in (
            candidate.test_data,
            *(unit.extra_test_data for unit in units),
            *(note for unit in units for note in (unit.technical_notes or [])),
        )
        if part
    ]
    parsed = parse_scenario_clauses(primary.body or "")
    notes.extend(parsed["technical"])
    intent = primary.test_intent or build_test_intent(primary.scenario)
    if intent and intent not in " ".join(notes):
        notes.append(f"Intención de prueba: {intent}")
    candidate.test_data = "; ".join(dict.fromkeys(notes)) or None
    unit_action = _action_from_unit(primary)
    current_action = (candidate.steps[0].action if candidate.steps else "") or ""
    if is_user_action(current_action) and not step_smuggles_condition(current_action):
        action = current_action
    elif is_user_action(unit_action) and not step_smuggles_condition(unit_action):
        action = unit_action
    else:
        action = STABLE_GENERIC_STEP
    unit_expected = _expected_from_unit(primary, name)
    if not candidate.steps:
        candidate.steps = [CandidateStep(step_number=1, action=action, expected_result=unit_expected)]
    else:
        for index, step in enumerate(candidate.steps, start=1):
            step.step_number = index
            step.action = action
            if not step.expected_result or is_generic_expected(step.expected_result):
                step.expected_result = unit_expected
    rules = list(candidate.applied_rules or [])
    if "executability-reconstruct" not in rules:
        rules.append("executability-reconstruct")
    candidate.applied_rules = rules
    candidate.review_required = True
    return candidate


def bind_condition_outside_step(candidate: GeneratedCaseCandidate) -> GeneratedCaseCandidate:
    """Last-resort / no unit: keep B in precondition, A generic, C honest."""
    name = candidate.name or ""
    clause = condition_clause(name)
    titled = _title_as_condition(name)
    if titled and not candidate.precondition:
        candidate.precondition = titled
    elif clause and not candidate.precondition and _CONDITIONISH.search(clause):
        prepared = clause[0].upper() + clause[1:]
        candidate.precondition = prepared + ("." if not prepared.endswith(".") else "")
    for step in candidate.steps:
        if step_smuggles_condition(step.action) or not is_user_action(step.action):
            if not is_stable_generic_step(step.action):
                step.action = STABLE_GENERIC_STEP
        if is_generic_expected(step.expected_result) or step_smuggles_condition(step.expected_result or ""):
            step.expected_result = bound_expected(name, None)
    rules = list(candidate.applied_rules or [])
    if "executability-bind-bac" not in rules:
        rules.append("executability-bind-bac")
    candidate.applied_rules = rules
    return candidate


def apply_bac_to_candidate(candidate: GeneratedCaseCandidate) -> GeneratedCaseCandidate:
    """Normalize one candidate so Step is not B and not B mixed into A."""
    extras_b: list[str] = []
    extras_c: list[str] = []
    extras_d: list[str] = []
    new_steps: list[CandidateStep] = []
    user_action: str | None = None
    for step in candidate.steps or []:
        action = (step.action or "").strip()
        if step.test_data:
            extras_d.append(step.test_data)
        if is_user_action(action) and not step_smuggles_condition(action):
            user_action = action
            new_steps.append(step)
            continue
        if is_stable_generic_step(action):
            new_steps.append(step)
            continue
        if is_state_observation(action):
            extras_c.append(action)
            continue
        smuggled = extract_smuggled_condition(action)
        if smuggled:
            extras_b.append(smuggled)
        if step_smuggles_condition(action) or is_technical_action(action) or is_generic_action(action):
            if not smuggled:
                extras_d.append(action)
            continue
        extras_b.append(action)
    action = user_action or STABLE_GENERIC_STEP
    if not new_steps:
        expected = (candidate.steps[0].expected_result if candidate.steps else "") or ""
        if extras_c and (not expected or is_generic_expected(expected)):
            expected = extras_c[0]
            extras_c = extras_c[1:]
        new_steps = [CandidateStep(step_number=1, action=action, expected_result=expected)]
    else:
        for step in new_steps:
            step.action = user_action or step.action
        if extras_c:
            first = new_steps[0]
            if not first.expected_result or is_generic_expected(first.expected_result):
                first.expected_result = extras_c.pop(0)
            for extra in extras_c:
                new_steps.append(
                    CandidateStep(
                        step_number=len(new_steps) + 1,
                        action=action,
                        expected_result=extra,
                    )
                )
    for index, step in enumerate(new_steps, start=1):
        step.step_number = index
        if is_generic_expected(step.expected_result):
            step.expected_result = bound_expected(candidate.name or "", step.expected_result)
        if step_smuggles_condition(step.action) or is_state_observation(step.action):
            step.action = STABLE_GENERIC_STEP
        if not is_user_action(step.action) and not is_stable_generic_step(step.action):
            step.action = STABLE_GENERIC_STEP
    candidate.steps = new_steps
    if extras_b:
        extra_pre = "; ".join(dict.fromkeys(extras_b))
        candidate.precondition = "; ".join(
            part for part in (candidate.precondition, extra_pre) if part
        )
    if extras_d:
        candidate.test_data = "; ".join(
            dict.fromkeys(part for part in [candidate.test_data, *extras_d] if part)
        )
    return candidate


def apply_executability_gate(
    candidates: list[GeneratedCaseCandidate],
    inventory: list[CoverageUnit] | None = None,
) -> list[GeneratedCaseCandidate]:
    """Never drop coverage. Rebuild B/A/C if the step mixed condition into the action."""
    by_id = {unit.coverage_id: unit for unit in inventory or []}
    out: list[GeneratedCaseCandidate] = []
    for candidate in candidates:
        origin = candidate.generation_origin or ""
        if origin in {"composed-flow", "llm"} or any(
            str(rule).startswith("composed-flow") for rule in (candidate.applied_rules or [])
        ):
            candidate.precondition = normalize_precondition(candidate.precondition)
            out.append(candidate)
            continue
        units = [by_id[cid] for cid in (candidate.covers or []) if cid in by_id]
        if units:
            reconstruct_from_units(candidate, units)
        apply_bac_to_candidate(candidate)
        needs = step_needs_bac_fix(candidate) or expected_hides_observation(candidate)
        missing = differential_missing(candidate, units) if units else False
        if units and (needs or missing):
            reconstruct_from_units(candidate, units)
            apply_bac_to_candidate(candidate)
        elif not units:
            bind_condition_outside_step(candidate)
        candidate.precondition = normalize_precondition(candidate.precondition)
        out.append(candidate)
    return out
