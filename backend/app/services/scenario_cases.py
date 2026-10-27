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
from app.services.qc_eligibility import is_robust_consumption, split_visible_technical

_EVENT_THEN = re.compile(
    r"\b(se env[ií]a|se registra|se dispara|se reporta|se llama|se emite|debe emitirse).{0,80}\b(evento|m[eé]trica|servicio|api|endpoint)\b",
    re.I,
)
_SYSTEM_WHEN = re.compile(
    r"\b(procesa|procesar|decodifica|decodificar|parsea|parsear|reintenta|reintentar)\b|"
    r"\b(el sistema|la aplicaci[oó]n|el servicio|el backend)\s+(env[ií]a|enviar|procesa|decodifica|parsea|reintenta)\b",
    re.I,
)
_STATE_THEN = re.compile(
    r"\b(fue|fueron|queda|qued[oó]|est[aá]|est[aá]n|permanece|resulta|ha sido)\b",
    re.I,
)
_UI_THEN = re.compile(r"\b(muestra|mostrar|mensaje|pantalla|bot[oó]n|modal|tooltip|men[uú])\b", re.I)
_NAV_GIVEN = re.compile(
    r"\b(abre|abrir|ingresa|ingresar|navega|navegar|selecciona|seleccionar|entra a|entrar|accede|acceder)\b",
    re.I,
)
_INPUT_FIELD = re.compile(
    r"\b(?:ingresa|ingresar|escribe|escribir|completa|completar|digita|digitar|captura|capturar)"
    r"\s+(?:el |la |los |las |un |una )?([^\",.;]{2,40})",
    re.I,
)
_TECH_PRE = re.compile(
    r"\b(sdk|librer[ií]a|inicializ\w*|endpoint|\bapi\b|feature\s*:|implementaci[oó]n|"
    r"contexto global|convenci[oó]n)\b",
    re.I,
)
_FULL_IDENT = re.compile(
    r"`[^`]+`"
    r"""|["“][^"”]*[.=][^"”]*["”]"""
    r"|https?://\S+"
    r"|/[A-Za-z0-9._\-/]+"
    r"|\b[\w.]+\s*=\s*[\w.]+\b"
    r"|\b[A-Za-z][\w]*(?:[._][A-Za-z0-9]+)+\b"
)


def composition_mode() -> str:
    raw = (getattr(settings, "case_composition_mode", None) or "scenario").strip().lower()
    return raw if raw in {"scenario", "flow"} else "scenario"


def scenario_group_key(unit: CoverageUnit) -> str:
    grouped = (unit.scenario_group or "").strip()
    if grouped and "|scenario|" not in grouped:
        return grouped
    blob = f"{unit.scenario or ''}\n{unit.body or ''}"
    if re.search(r"no se logra obtener|se encuentra vac[ií]a|valor (ausente|vac[ií]o)", blob, re.I):
        return f"{unit.artifact_key or unit.rn_key or ''}|robustez-consumo"
    base = re.sub(r"\s*\([^)]*\)\s*$", "", unit.scenario or "").strip()
    return f"{unit.story_key or unit.jira_key}|{base}"


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


_LINT_TECH = re.compile(
    r"\b(servicio|API|llamad[oa]|petici[oó]n|invoca|endpoint|request|metadata|"
    r"valor recibido|llave de configuraci[oó]n|se recupera del|\blog\b|"
    r"evento [a-z]+\.[a-z]+)\b",
    re.I,
)
_LINT_GEN = re.compile(
    r"Se muestra el resultado de|comportamiento definido|cambio en esa pantalla|Abrir y presenta",
    re.I,
)


def _scrub_visible(text: str | None, title: str = "", fallback: str = "") -> str:
    out = re.sub(r"@([A-Za-z_]\w*)", r"\1", text or "")
    out = re.sub(r"<[^>]{0,40}>", " ", out)
    out = _LINT_TECH.sub(" ", out)
    if _LINT_GEN.search(out):
        out = fallback or "Se observa el resultado en el dispositivo"
    out = re.sub(r"\s+", " ", out).strip(" .;,-")
    title_n = re.sub(r"^\s*\d+\.\s*", "", title or "").strip().lower()[:40]
    body_n = out.lower()[:40]
    if title_n and body_n == title_n:
        out = fallback or "Se observa el resultado en el dispositivo"
    if re.match(r"se muestra verificar\b", out, re.I):
        out = fallback or "Se observa el resultado en el dispositivo"
    return out


def lift_technical(text: str | None) -> tuple[str, list[str]]:
    """Move a technical identifier out whole. Visible text keeps no fragment."""
    found: list[str] = []

    def _grab(match: re.Match[str]) -> str:
        token = match.group(0).strip().strip("`").strip("\"“”")
        token = re.sub(r"\s+", " ", token).strip(" .;")
        if token:
            found.append(token)
        return " "

    cleaned = _FULL_IDENT.sub(_grab, text or "")
    cleaned = re.sub(r'["“]\s*[.\s=]*["”]', " ", cleaned)
    cleaned = re.sub(r"\s*[.](?:\s*[.])+\s*", " ", cleaned)
    cleaned = re.sub(r"\s+=\s*", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .;,-:\"“”")
    return cleaned, list(dict.fromkeys(found))


def render_expected(text: str | None) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    if _STATE_THEN.search(raw) and not _UI_THEN.search(raw):
        raw = re.sub(r'["“]([^"”]+)["”]', r"\1", raw)
        raw = re.sub(r"se muestra el mensaje\s*", "", raw, flags=re.I).strip()
        if raw:
            raw = raw[0].upper() + raw[1:]
        if raw and not raw.endswith("."):
            raw += "."
        return re.sub(r"\s+", " ", raw).strip()
    return polish_expected(raw)


def visible_outcome(*sources: str | None) -> str:
    for source in sources:
        text = strip_title_prefix(source or "")
        text = re.sub(r"^\s*feature\s*:?\s*", "", text, flags=re.I).strip(" .")
        match = re.match(r"carga exitosa del\s+(.+)", text, flags=re.I)
        if match:
            return f"Se muestra el {match.group(1).strip()} con sus contenidos."
        match = re.match(r"carga exitosa de la\s+(.+)", text, flags=re.I)
        if match:
            return f"Se muestra la {match.group(1).strip()} con sus contenidos."
    for source in sources:
        text = strip_title_prefix(source or "")
        if _UI_THEN.search(text) and not _EVENT_THEN.search(text):
            rendered = render_expected(text)
            if rendered:
                return rendered
    return ""


def _arrival_result(clause: str) -> str:
    dest = re.sub(
        r"^.*?\b(abre|abrir|ingresa a|ingresar a|ingresa|ingresar|navega a|navegar a|navega|navegar|"
        r"selecciona|seleccionar|entra a|entrar a|entra|accede a|acceder a|accede|acceder)\b\s*",
        "",
        clause or "",
        count=1,
        flags=re.I,
    ).strip(" .")
    dest = re.sub(r'["“]([^"”]+)["”]', r"\1", dest)
    dest, _idents = lift_technical(dest)
    if not dest:
        return ""
    return f"Se muestra {dest}."


def _navigation_steps(text: str) -> list[tuple[str, str]]:
    steps: list[tuple[str, str]] = []
    for kind, clause in _walk_gwt(text or ""):
        if kind not in {"given", "when"}:
            continue
        clause = re.sub(r"^(?:que|de que)\s+", "", clause, flags=re.I).strip()
        is_nav = bool(_NAV_GIVEN.search(clause))
        if kind == "given" and not is_nav:
            continue
        action = _nav_action(clause) or to_infinitive(clause)
        if not action or not is_tester_action(action):
            continue
        if kind == "when" and not is_nav and not is_user_action(clause):
            continue
        steps.append((action, _arrival_result(clause)))
    return steps


def _missing_data(walked: list[tuple[str, str]], source: str) -> list[str]:
    notes: list[str] = []
    blob = source or ""
    for kind, text in walked:
        if kind != "when" or _QUOTED.search(text or ""):
            continue
        match = _INPUT_FIELD.search(text or "")
        if not match:
            continue
        field = re.sub(r"\s+(con|para|en|y|del|de)\b.*", "", match.group(1), flags=re.I).strip()
        if len(field) < 2:
            continue
        if re.search(rf"\b{re.escape(field)}\b.{{0,30}}[:=]", blob, re.I):
            continue
        note = f"Definir por QC: {field}"
        if note.lower() not in blob.lower():
            notes.append(note)
    return list(dict.fromkeys(notes))


def _action_from_title(title: str) -> str:
    raw = strip_title_prefix(title or "")
    raw = re.sub(
        r"^(visualizaci[oó]n de| construcci[oó]n de|mostrar|implementaci[oó]n de)\s+",
        "",
        raw,
        flags=re.I,
    ).strip()
    inf = to_infinitive(raw)
    if is_tester_action(inf):
        return inf
    if raw:
        return f"Verificar {raw[0].lower() + raw[1:]}" if raw else ""
    return ""


def _short_phrase(text: str | None, limit: int = 6) -> str:
    raw = re.sub(r"^\s*feature\s*:?\s*", "", (text or ""), flags=re.I).strip(" .:-")
    words = [word for word in re.split(r"\s+", raw) if word]
    return " ".join(words[:limit])


def compose_scenario_units(units: list[CoverageUnit]) -> FlowDraft:
    primary = units[0]
    walked: list[tuple[str, str]] = []
    seen_bodies: set[str] = set()
    for unit in units:
        evidence_body = (unit.evidence or "").split("\n", 1)
        body = evidence_body[1] if len(evidence_body) > 1 else (unit.body or "")
        if body in seen_bodies:
            continue
        seen_bodies.add(body)
        walked.extend(_walk_gwt(body))
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
        visible, technical = split_visible_technical(f"Then {text}", "")
        for item in technical:
            tech.append(item)
            if TECH_VERIFY_MARK not in tech:
                tech.append(TECH_VERIFY_MARK)
        if not visible:
            if technical or _TECH_RESULT.search(text or "") or _ENDPOINT.search(text or "") or _EVENT_THEN.search(text or ""):
                return
            visible = [text] if text else []
        cleaned = polish_expected("; ".join(visible))
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
            if re.match(r"^\s*(que )?accede", text, re.I):
                rest = re.sub(r"^\s*(que )?accede( a| al|)\s*", "", text, flags=re.I).strip()
                nav.append(f"Estar en {rest}".strip())
                continue
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
            story_lead = _short_phrase(primary.story_summary, limit=8).lower()
            if story_lead and story_lead in action.lower():
                continue
            if re.match(r"^\s*(implementar |se muestra el resultado de:)", action, re.I):
                continue
            expected = polish_expected("; ".join(pending_then)) if pending_then else ""
            pending_then = []
            existing = next(
                (step for step in steps if (step.action or "").lower() == action.lower()),
                None,
            )
            if existing:
                if expected:
                    existing.expected_result = polish_expected(
                        "; ".join(part for part in (existing.expected_result, expected) if part)
                    )
                continue
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
    for kind, text in walked:
        if kind != "given":
            continue
        if _NAV_GIVEN.search(text) or _TECH_RESULT.search(text) or _ENDPOINT.search(text):
            continue
        rest = re.sub(
            r"^\s*((el|la) usuario\s+)?(está|esta|se encuentra|se halla|tiene)(\s+en)?\s+",
            "",
            text,
            flags=re.I,
        ).strip()
        if not rest or rest.lower() == (text or "").strip().lower():
            continue
        entry = f"Estar en {rest}"
        if any(entry.lower() == (step.action or "").lower() for step in steps):
            break
        steps.insert(
            0,
            CandidateStep(step_number=1, action=entry, expected_result="", covered_unit_ids=list(covers)),
        )
        break
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
                steps.append(
                    CandidateStep(
                        step_number=1,
                        action=fallback,
                        expected_result=visible,
                        covered_unit_ids=list(covers),
                    )
                )
                break
    if not system_when and not any(is_tester_action(step.action) for step in steps) and nav:
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
    visible_then = any(
        kind == "then"
        and text
        and not _EVENT_THEN.search(text)
        and not (_TECH_RESULT.search(text) or _ENDPOINT.search(text))
        for kind, text in walked
    )
    when_is_system = system_when or any(
        kind == "when" and _SYSTEM_WHEN.search(text) and not is_user_action(text) for kind, text in walked
    )
    if not any(is_tester_action(step.action) for step in steps):
        title_action = _action_from_title(primary.scenario or "")
        given_action = next(iter(nav), "")
        fallback = given_action or title_action
        if fallback:
            steps.append(
                CandidateStep(
                    step_number=1,
                    action=fallback,
                    expected_result=merged_expected or polish_expected("; ".join(pending_then)),
                    covered_unit_ids=list(covers),
                )
            )
        elif when_is_system and not visible_then:
            pending = "verificación técnica"
            steps = []
    for action, result in _navigation_steps(primary.feature_background or ""):
        if any((step.action or "").lower() == action.lower() for step in steps):
            for step in steps:
                if (step.action or "").lower() == action.lower() and not step.expected_result:
                    step.expected_result = result
            continue
        if not steps and when_is_system and not visible_then:
            continue
        steps.insert(
            0,
            CandidateStep(step_number=1, action=action, expected_result=result, covered_unit_ids=list(covers)),
        )
    if len(steps) == 1:
        given_nav = next((item for item in nav if item), "")
        extra = ""
        if given_nav and given_nav.lower() != (steps[0].action or "").lower():
            extra = given_nav
        if extra:
            steps.insert(
                0,
                CandidateStep(
                    step_number=1,
                    action=extra,
                    expected_result=_arrival_result(extra),
                    covered_unit_ids=list(covers),
                ),
            )
    for step in steps:
        if _NAV_GIVEN.search(step.action or "") and not (step.expected_result or "").strip():
            step.expected_result = _arrival_result(step.action)
        action_clean, action_ids = lift_technical(step.action)
        expected_clean, expected_ids = lift_technical(step.expected_result)
        tech.extend(action_ids)
        tech.extend(expected_ids)
        visible_fallback = polish_expected("; ".join(pending_then)) or merged_expected
        step.action = _scrub_visible(action_clean or step.action, primary.scenario or "", "Abrir la aplicación")
        step.expected_result = _scrub_visible(
            render_expected(expected_clean or step.expected_result),
            primary.scenario or "",
            visible_fallback,
        )
        if _EVENT_THEN.search(step.expected_result or "") or re.search(r"debe emitirse el evento", step.expected_result or "", re.I):
            outcome = visible_outcome(primary.scenario, primary.story_summary)
            if outcome and is_tester_action(step.action):
                step.expected_result = outcome
                if TECH_VERIFY_MARK not in tech:
                    tech.append(TECH_VERIFY_MARK)
    if any(is_tester_action(step.action) for step in steps):
        for step in steps:
            if is_tester_action(step.action) and not (step.expected_result or "").strip():
                outcome = visible_outcome(primary.scenario, primary.story_summary)
                if outcome and any(_EVENT_THEN.search(item) or "evento" in item.lower() for item in tech):
                    step.expected_result = outcome
                    if TECH_VERIFY_MARK not in tech:
                        tech.append(TECH_VERIFY_MARK)
    for index, step in enumerate(steps, start=1):
        step.step_number = index
        if step.expected_result and not _STATE_THEN.search(step.expected_result):
            step.expected_result = polish_expected(step.expected_result) or step.expected_result
    if len(steps) == 1:
        only = steps[0]
        if not re.match(r"^\s*abrir la aplicaci[oó]n\b", only.action or "", re.I):
            steps.insert(
                0,
                CandidateStep(
                    step_number=1,
                    action="Abrir la aplicación",
                    expected_result="Se muestra la pantalla de partida",
                    covered_unit_ids=list(covers),
                ),
            )
    if "impacto-superficie" in (primary.applied_rules or []):
        visible = (primary.observable_then or [primary.behavior or primary.scenario])[0]
        title = re.sub(r"^se muestra\s+", "", visible or "", flags=re.I).strip()[:120]
        title = title[:1].upper() + title[1:] if title else strip_title_prefix(primary.scenario)
    else:
        title_clean, title_ids = lift_technical(strip_title_prefix(primary.scenario))
        tech.extend(title_ids)
        title = (title_clean or strip_title_prefix(primary.scenario))[:120]
    kept_pre: list[str] = []
    story_title = _short_phrase(primary.story_summary, limit=12)
    for clause in pre:
        clause_clean, clause_ids = lift_technical(clause)
        tech.extend(clause_ids)
        if not clause_clean:
            continue
        if _TECH_PRE.search(clause_clean) or (
            story_title and _short_phrase(clause_clean, limit=12).lower() == story_title.lower()
        ):
            tech.append(clause_clean)
            continue
        kept_pre.append(clause_clean)
    data_notes = _missing_data(walked, "\n".join(unit.extra_test_data or "" for unit in units))
    test_data = _examples_as_data(units)
    if data_notes:
        test_data = "; ".join(part for part in [test_data, *data_notes] if part)
    tech_notes = list(dict.fromkeys([*tech, *(note for unit in units for note in (unit.technical_notes or []))]))
    rules = ["scenario-case", *{
        rule
        for unit in units
        for rule in (unit.applied_rules or [])
        if rule in {"verificacion-tecnica", "regresion-funcional", "na-ambiente", "impacto-superficie"}
        or str(rule).startswith("pendiente-qc")
    }]
    if pending == "verificación técnica" and "verificacion-tecnica" not in rules:
        rules.append("verificacion-tecnica")
    if "|robustez-consumo" in (primary.scenario_group or "") or all(
        is_robust_consumption(unit.scenario or "", unit.body or "") for unit in units
    ):
        title = "Valor de configuración ausente o vacío"
        kept_pre = list(dict.fromkeys([*kept_pre, "requiere apoyo Dev/Operación"]))
    return FlowDraft(
        story_key=primary.story_key or primary.jira_key or "",
        epic_key=primary.artifact_key or primary.rn_key or "",
        units=units,
        title=title,
        precondition=normalize_precondition("; ".join(dict.fromkeys(kept_pre))),
        steps=steps,
        test_data=test_data,
        pending_reason=pending,
        evidence=primary.evidence or title,
        applied_rules=rules,
        technical_reference="; ".join(part for part in tech_notes if part) or None,
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
        if key.endswith("|robustez-consumo"):
            rows = ["Condición | Resultado esperado"]
            for unit in groups[key]:
                rows.append(
                    f"{unit.story_key or unit.scenario} | "
                    f"{_unit_expected(unit) or unit.scenario or ''}"
                )
            if len(rows) > 2:
                candidate.variant_table = "\n".join(rows)
            candidate.requires_condition = True
            candidate.precondition = draft.precondition
        candidate.applied_rules = list(dict.fromkeys([*(candidate.applied_rules or []), *(draft.applied_rules or [])]))
        out.append(candidate)
    exe = {
        ((row.related_jira or "").split(" | ")[0], re.sub(r"\W+", " ", (row.name or "").lower()).strip())
        for row in out
        if (row.applicability or "ejecutable") != "na_ambiente" and row.steps
    }
    filtered: list[GeneratedCaseCandidate] = []
    for row in out:
        ident = (
            (row.related_jira or "").split(" | ")[0],
            re.sub(r"\W+", " ", (row.name or "").lower()).strip(),
        )
        if (row.applicability or "") == "na_ambiente" and ident in exe:
            continue
        filtered.append(row)
    return contextualize_duplicate_titles(filtered)


def feature_context(candidate: GeneratedCaseCandidate) -> str:
    raw = _short_phrase(candidate.use_case_title or candidate.description or "")
    if not raw:
        return ""
    if re.sub(r"\W+", " ", raw.lower()).strip() == re.sub(r"\W+", " ", (candidate.name or "").lower()).strip():
        return ""
    if raw.lower() in (candidate.name or "").lower():
        return ""
    return raw


def contextualize_duplicate_titles(candidates: list[GeneratedCaseCandidate]) -> list[GeneratedCaseCandidate]:
    grouped: dict[str, list[GeneratedCaseCandidate]] = {}
    order: list[str] = []
    for candidate in candidates:
        epic = (candidate.related_functionality or "").split(" | ")[0].strip()
        base = re.sub(r"\s+—\s+.*$", "", strip_title_prefix(candidate.name)).strip()
        normalized = re.sub(r"\W+", " ", base.lower()).strip()
        key = f"{epic}|{normalized}"
        if key not in grouped:
            order.append(key)
        grouped.setdefault(key, []).append(candidate)
    fused: list[GeneratedCaseCandidate] = []
    for key in order:
        rows = grouped[key]
        keep = rows[0]
        if len(rows) > 1:
            variants = [keep.variant_table or ""]
            covers = list(keep.covers or keep.covered_unit_ids or [])
            for extra in rows[1:]:
                covers.extend(extra.covers or extra.covered_unit_ids or [])
                if extra.variant_table:
                    variants.append(extra.variant_table)
                extra_data = getattr(extra, "test_data", None) or getattr(extra, "extra_test_data", None)
                if extra_data:
                    keep.test_data = "; ".join(
                        part for part in (getattr(keep, "test_data", None), extra_data) if part
                    )
            keep.covers = list(dict.fromkeys(covers))
            keep.covered_unit_ids = list(keep.covers)
            table = [line for blob in variants for line in str(blob).splitlines() if line.strip()]
            if len(rows) > 1:
                keep.variant_table = "\n".join(dict.fromkeys(table)) or keep.variant_table
            keep.name = re.sub(r"\s+—\s+.*$", "", strip_title_prefix(keep.name)).strip()[:120]
        fused.append(keep)
    return fused


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
    seen: dict[tuple[str, str], int] = {
        (str(row.get("story") or ""), str(row.get("scenario") or "")): index
        for index, row in enumerate(stats.scenario_ledger)
    }
    for unit in inventory:
        if (unit.source_origin or "gherkin") != "gherkin":
            continue
        scenario = re.sub(r"\s*\([^)]*\)\s*$", "", unit.scenario or "").strip()
        key = (unit.story_key or "", scenario)
        if key in seen:
            prior = stats.scenario_ledger[seen[key]]
            match = covered.get(unit.coverage_id)
            if match and match.steps and prior.get("estado") != "caso ejecutable":
                prior["estado"] = "caso ejecutable"
                prior["motivo"] = ""
                prior["case_id"] = match.name
            continue
        seen[key] = len(stats.scenario_ledger)
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
        elif match and match.steps:
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
                "verificación técnica",
                (match.applicability_reason if match else None)
                or "sin Then observable o sin acción de tester derivable",
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
    group_to_case: dict[str, str] = {}
    for unit in inventory:
        match = covered.get(unit.coverage_id)
        if match and match.steps and unit.scenario_group:
            group_to_case[unit.scenario_group] = match.name
    note_prefix = "cubierto por"
    for row in stats.scenario_ledger:
        if str(row.get("estado") or "") != "verificación técnica":
            continue
        group = str(row.get("surface_group") or "")
        cover = group_to_case.get(group)
        if not cover:
            continue
        motivo = str(row.get("motivo") or "")
        if note_prefix in motivo:
            continue
        row["motivo"] = f"{motivo}; cubierto por {cover}".strip("; ")
