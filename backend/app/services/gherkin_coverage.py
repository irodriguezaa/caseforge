"""Evidence-backed scenario materialization from Jira Gherkin.

Does not invent scenarios. Scenario Outline Examples that are only HTTP codes with no
evidenced UX difference are grouped (HANDOFF). Distinct example values that are not
HTTP-only are materialized as independent functional conditions.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from app.schemas.case_generation import (
    CandidateStep,
    CoverageUnit,
    GeneratedCaseCandidate,
    GenerationStats,
)
from app.services.executability import (
    STABLE_GENERIC_STEP,
    apply_executability_gate,
    build_test_intent,
    is_stable_generic_step,
    is_user_action,
    parse_scenario_clauses,
)
from app.services.qc_candidate_rules import (
    apply_qc_rules,
    classify_confidence,
    classify_priority,
    example_strategy,
    format_examples,
    functional_title,
    group_examples_by_outcome,
)
from app.services.scenario_classifier import (
    ScenarioClassification,
    _has_observable_consequence,
    _is_generic_then,
    classify_scenario,
    record_classification,
)

_SCENARIO_SPLIT = re.compile(
    r"^\s*(Scenario Outline|Scenario|Escenario esquemático|Escenario)\s*:\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_EXAMPLES_SPLIT = re.compile(
    r"^\s*Examples?\s*:\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_QUALITY_APPENDIX = re.compile(
    r"Criterios de calidad(?: y prueba)?",
    re.IGNORECASE,
)
_HTTP_CODE = re.compile(r"^\d{3}$")
_GIVEN = re.compile(r"^\s*(Given|Dado que|Dado)\s+", re.IGNORECASE)
_WHEN = re.compile(r"^\s*(When|Cuando)\s+", re.IGNORECASE)
_THEN = re.compile(r"^\s*(Then|Entonces)\s+", re.IGNORECASE)
_TECHNICAL = re.compile(
    r"\b(GET|POST|PUT|PATCH|DELETE)\b|"
    r"https?://\S+|"
    r"/services/[^\s]+|"
    r"/[a-z]+/v\d+/[^\s]+|"
    r"/[a-z][a-z0-9_\-/]{2,}|"
    r"\bstatus codes?\b|"
    r"\bHTTP\b|"
    r"\binvoca\b|"
    r"module_version|"
    r"`[^`]+`|"
    r"""["'][A-Za-z_][A-Za-z0-9_]*["']""",
    re.IGNORECASE,
)
_CAMEL_FIELD = re.compile(
    r"\b[a-z][a-zA-Z0-9]*[A-Z][A-Za-z0-9]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*"
)


def sanitize_user_text(text: str) -> str:
    cleaned = _TECHNICAL.sub(" ", text or "")
    cleaned = _CAMEL_FIELD.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" :;-")
    return cleaned


def extract_technical(text: str) -> str:
    found = [match.group(0) for match in _TECHNICAL.finditer(text or "")]
    found.extend(match.group(0) for match in _CAMEL_FIELD.finditer(text or ""))
    return ", ".join(dict.fromkeys(found))


def gherkin_source_text(description: str) -> str:
    """Keeps Feature/Scenario Gherkin and drops the quality-criteria appendix.

    Those sections state they are not specific test cases (HANDOFF: not every Jira detail is a TC).
    """
    if not description:
        return ""
    match = _QUALITY_APPENDIX.search(description)
    if match:
        return description[: match.start()].strip()
    return description.strip()


def _block_dedupe_key(block: dict[str, Any]) -> str:
    title = re.sub(r"\s+", " ", (block.get("title") or "").strip().lower())
    body = re.sub(r"\s+", " ", (block.get("body") or "").strip().lower())
    return f"{title}\n{body}"


def extract_gherkin_blocks(description: str, acceptance_criteria: str = "") -> list[dict[str, Any]]:
    """Scenario blocks from description and/or acceptance criteria, without duplicates."""
    blocks: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in (description, acceptance_criteria):
        text = gherkin_source_text(raw or "")
        if not text:
            continue
        for block in parse_gherkin_blocks(text):
            key = _block_dedupe_key(block)
            if not key.strip() or key in seen:
                continue
            seen.add(key)
            block.setdefault("source_origin", "gherkin")
            blocks.append(block)
    return blocks


_USER_WHEN = re.compile(
    r"\b((el )?usuario)\b.{0,100}\b("
    r"selecciona|presiona|ingresa|pulsa|abre|cierra|digita|navega|"
    r"agrega|elimina|desbloquea|graba|cancela|reproduce|da clic|hace clic"
    r")\b|"
    r"\b(CH\+|CH-|Back|OK)\b",
    re.IGNORECASE,
)
_SATELLITE_OBS = re.compile(
    r"no (debe |se )?(mostrarse|mostrar|presentar).{0,80}error|"
    r"texto de error visible|"
    r"status codes?|"
    r"\bHTTP\b \d{3}|"
    r"tama[nñ]o de los elementos.{0,40}fijo|"
    r"estructura actual de la pantalla|"
    r"layout aprobado|"
    r"se mantiene la estructura",
    re.IGNORECASE,
)
_INVENTORY_THEN_UX = re.compile(
    r"se reproduce|reproducci[oó]n|pausa(r)? (la )?reproduc|"
    r"reanuda|"
    r"\bcanal\b|"
    r"panel de (audio|metadata)|"
    r"audio actual|subt[ií]tulo actual|"
    r"cambio de audio|"
    r"se identifica el (audio|subt)|"
    r"d[ií]gitos|dashes|"
    r"PIN de seguridad|favoritos|desbloquear|"
    r"digitaci[oó]n|CH\+|primer acceso|"
    r"por default|por defecto|valor por defecto|"
    r"reflej|"
    r"no (deben )?verse afectadas|no afecta otras|"
    r"textos (y valores )?configurables|"
    r"subt[ií]tul|desactiv|"
    r"permanece (abierto|desplegado)|"
    r"\bcheck\b|"
    r"preferencia",
    re.IGNORECASE,
)
_HTTP_API_LINE = re.compile(
    r"\b(GET|POST|PUT|PATCH|DELETE)\b|"
    r"/[a-z][a-z0-9_\-/]{2,}|"
    r"\bstatus codes?\b|"
    r"\bHTTP\b",
    re.IGNORECASE,
)
_PURE_CONFIG_LINE = re.compile(
    r"feature flag|llave de configuraci[oó]n|module_version|"
    r"apa/metadata|objeto ['\"]default['\"]",
    re.IGNORECASE,
)
_PROSE_UX = re.compile(
    r"continuidad|no se ve afect|no (deben )?verse afectadas|no afecta otras|"
    r"comportamiento por defecto|por defecto del dispositivo|comportamiento esperado del dispositivo|"
    r"reflej|textos (y valores )?configurables|player vod|"
    r"se (muestra|visualiza|reproduce|pausa|oculta|restaura)",
    re.IGNORECASE,
)
_BACKGROUND = re.compile(r"^\s*Background\s*:", re.IGNORECASE | re.MULTILINE)
_DEFECT_NARRATIVE = re.compile(
    r"^\s*(obtenido|esperado)\s*:|"
    r"\bse encontr[oó] que\b|"
    r"\bse detecta que\b|"
    r"\bdetectamos que\b",
    re.IGNORECASE,
)
_TECH_IMPL_ONLY = re.compile(
    r"\bappkeys\b|"
    r"\bstream types?\b|"
    r"track/dubsubchange|"
    r"\bb1\+[A-Z]+CL-\d+",
    re.IGNORECASE,
)
_TABLE_ATOM = re.compile(r"^.+:.+$")


def _http_or_api_only(text: str) -> bool:
    if _has_observable_consequence(text):
        return False
    return bool(_HTTP_API_LINE.search(text or ""))


def _pure_config_only(text: str) -> bool:
    if _has_observable_consequence(text) or _PROSE_UX.search(text or ""):
        return False
    return bool(_PURE_CONFIG_LINE.search(text or ""))


def _defect_narrative_without_user(title: str, body: str, user_action: str | None) -> bool:
    blob = f"{title or ''}\n{body or ''}"
    if not _DEFECT_NARRATIVE.search(blob):
        return False
    return not bool((user_action or "").strip())


def _implementation_without_ux(title: str, body: str, user_action: str | None) -> bool:
    blob = f"{title or ''}\n{body or ''}"
    if _has_observable_consequence(blob) or _PROSE_UX.search(blob) or (user_action or "").strip():
        return False
    return bool(_TECH_IMPL_ONLY.search(blob) or _pure_config_only(blob) or _http_or_api_only(blob))


def _non_qc_inventory_reason(
    title: str,
    body: str,
    user_action: str | None,
) -> str | None:
    blob = f"{title or ''}\n{body or ''}"
    if _http_or_api_only(blob):
        return "HTTP/API sin UX observable"
    if _pure_config_only(blob):
        return "configuración pura"
    if _defect_narrative_without_user(title, body, user_action):
        return "reporte de defecto sin acción de usuario ni CoverageUnit QC"
    if _implementation_without_ux(title, body, user_action):
        return "implementación técnica sin consecuencia observable"
    return None


def _text_without_scenarios(text: str) -> str:
    raw = gherkin_source_text(text or "")
    matches = list(_SCENARIO_SPLIT.finditer(raw))
    if matches:
        raw = raw[: matches[0].start()].strip()
    bg = _BACKGROUND.search(raw)
    if bg:
        raw = raw[: bg.start()].strip()
    return raw


def _dedupe_inventory_units(units: list[CoverageUnit]) -> list[CoverageUnit]:
    """Drop AC/description copies of an intent already covered by Gherkin. Never collapse Gherkin variants."""
    from app.services.functional_equivalence import build_functional_equivalence_key

    gherkin = [unit for unit in units if unit.source_origin == "gherkin"]
    others = [unit for unit in units if unit.source_origin != "gherkin"]
    seen = {build_functional_equivalence_key(unit).value() for unit in gherkin}
    kept_others: list[CoverageUnit] = []
    for unit in others:
        key = build_functional_equivalence_key(unit).value()
        if key in seen:
            continue
        seen.add(key)
        kept_others.append(unit)
    return gherkin + kept_others


def _is_satellite_observable(text: str) -> bool:
    return bool(_SATELLITE_OBS.search(text or ""))


def _is_table_atom(text: str) -> bool:
    stripped = (text or "").strip()
    return bool(_TABLE_ATOM.match(stripped) and ":" in stripped and len(stripped.split(":")) >= 2)


def _pick_user_action(clf: ScenarioClassification) -> str | None:
    candidates = [clf.qc_user_action, *(clf.when or [])]
    for raw in candidates:
        clause = (raw or "").strip()
        if not clause or is_stable_generic_step(clause):
            continue
        if is_user_action(clause) or _USER_WHEN.search(clause):
            return clause
    return None


def _focused_body(given: list[str], action: str | None, observable: str) -> str:
    lines: list[str] = []
    for index, clause in enumerate(given or []):
        prefix = "Given" if index == 0 else "And"
        lines.append(f"{prefix} {clause}")
    if action:
        lines.append(f"When {action}")
    lines.append(f"Then {observable}")
    return "\n".join(lines)


def _group_observable_atoms(observables: list[str]) -> list[list[str]]:
    """Keep Figma/table rows together; each other observable is its own atom group."""
    groups: list[list[str]] = []
    table_bucket: list[str] = []
    for item in observables:
        if _is_table_atom(item):
            table_bucket.append(item)
            continue
        if table_bucket:
            groups.append(table_bucket)
            table_bucket = []
        groups.append([item])
    if table_bucket:
        groups.append(table_bucket)
    return groups


def _prose_snippets(text: str) -> list[str]:
    snippets: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if _SCENARIO_SPLIT.match(line) or re.match(r"^Feature\s*:", line, re.I):
            continue
        line = re.sub(r"^[\-\*\d.\)\s]+", "", line).strip()
        if not line:
            continue
        for piece in re.split(r"(?<=[.!?])\s+", line):
            piece = piece.strip(" .;")
            if piece:
                snippets.append(piece)
    return snippets


def extract_prose_observable_blocks(
    description: str,
    acceptance_criteria: str,
    stats: GenerationStats,
    story_key: str = "",
) -> list[dict[str, Any]]:
    """Observable AC/description lines. Complementary to Gherkin; Scenarios are stripped, not used as a veto."""
    blocks: list[dict[str, Any]] = []
    seen: set[str] = set()
    for origin, raw in (
        ("description", description or ""),
        ("ac", acceptance_criteria or ""),
    ):
        text = _text_without_scenarios(raw)
        if not text:
            continue
        for snippet in _prose_snippets(text):
            key = re.sub(r"\s+", " ", snippet.lower())
            if key in seen:
                continue
            seen.add(key)
            label = f"{story_key}: {snippet[:80]}" if story_key else snippet[:80]
            if _http_or_api_only(snippet):
                stats.inventory_exclusions.append(f"{label}: HTTP/API sin UX observable")
                continue
            if _pure_config_only(snippet):
                stats.inventory_exclusions.append(f"{label}: configuración pura")
                continue
            action_match = _USER_WHEN.search(snippet)
            action = action_match.group(0).strip() if action_match else None
            noise = _non_qc_inventory_reason(snippet[:180], snippet, action)
            if noise:
                stats.inventory_exclusions.append(f"{label}: {noise}")
                continue
            body = _focused_body([], action, snippet)
            clf = classify_scenario(snippet[:180], body)
            explicit_ux = bool(
                _PROSE_UX.search(snippet)
                and re.search(
                    r"usuario|panel|player|experiencia|dispositivo|vod|pantalla|"
                    r"funcionalidades|comportamiento esperado|"
                    r"administraci[oó]n|herramienta de admin",
                    snippet,
                    re.I,
                )
            )
            if not _is_coverable(clf) and not (clf.observable_then or clf.qc_observables):
                if not explicit_ux:
                    stats.inventory_exclusions.append(
                        f"{label}: sin comportamiento observable ({clf.reason or clf.role})"
                    )
                    continue
                clf = replace(
                    clf,
                    role="G",
                    observable_then=[snippet],
                    qc_observables=[snippet],
                    qc_relevance="QC_FUNCTIONAL",
                )
            blocks.append(
                {
                    "title": snippet[:180],
                    "outline": False,
                    "body": body,
                    "examples": [],
                    "source_origin": "ac" if origin == "ac" else "description",
                }
            )
    return blocks


def parse_gherkin_blocks(description: str) -> list[dict[str, Any]]:
    if not description or not description.strip():
        return []
    matches = list(_SCENARIO_SPLIT.finditer(description))
    if not matches:
        return []
    blocks: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(description)
        kind = match.group(1).strip().lower()
        title = match.group(2).strip()
        body = description[match.end() : end].strip()
        is_outline = "outline" in kind or "esquemático" in kind
        examples = _parse_examples(body) if is_outline else []
        scenario_body = _EXAMPLES_SPLIT.split(body, maxsplit=1)[0]
        blocks.append(
            {
                "title": title,
                "outline": is_outline,
                "body": scenario_body.strip(),
                "examples": examples,
            }
        )
    return blocks


def _parse_examples(body: str) -> list[dict[str, str]]:
    parts = _EXAMPLES_SPLIT.split(body, maxsplit=1)
    if len(parts) < 2:
        return []
    rows: list[list[str]] = []
    for line in parts[1].splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            if rows:
                break
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if cells:
            rows.append(cells)
    if len(rows) < 2:
        return []
    headers = rows[0]
    examples: list[dict[str, str]] = []
    for row in rows[1:]:
        if not any(cell.strip() for cell in row):
            continue
        item = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
        examples.append(item)
    return examples


def _examples_are_http_same_behavior(examples: list[dict[str, str]]) -> bool:
    if not examples:
        return False
    values = []
    for example in examples:
        cells = [value.strip() for value in example.values() if value.strip()]
        if not cells:
            return False
        values.append(tuple(cells))
    codes_only = all(all(_HTTP_CODE.match(cell) for cell in row) for row in values)
    if codes_only:
        return True
    # One HTTP column plus identical extra columns → same observed behavior, group.
    extra_sets = []
    for row in values:
        extras = tuple(cell for cell in row if not _HTTP_CODE.match(cell))
        extra_sets.append(extras)
    http_present = any(any(_HTTP_CODE.match(cell) for cell in row) for row in values)
    return http_present and len(set(extra_sets)) <= 1


def _steps_from_body(body: str) -> tuple[str | None, list[CandidateStep], str | None]:
    parsed = parse_scenario_clauses(body)
    precondition_parts = [sanitize_user_text(part) or part for part in parsed["given"]]
    actions = [sanitize_user_text(part) or part for part in parsed["actions"]]
    expected = [sanitize_user_text(part) or part for part in parsed["expected"]]
    technical = [extract_technical(part) or part for part in parsed["technical"]]
    technical = [part for part in technical if part]
    steps: list[CandidateStep] = []
    if not expected:
        return (
            "; ".join(dict.fromkeys(p for p in precondition_parts if p)) or None,
            steps,
            "; ".join(dict.fromkeys(technical)) or None,
        )
    count = max(len(expected), 1)
    user_action = next((item for item in actions if item), "")
    for index in range(count):
        action = actions[index] if index < len(actions) else user_action
        result = expected[index] if index < len(expected) else expected[-1]
        steps.append(
            CandidateStep(
                step_number=index + 1,
                action=action,
                expected_result=result,
            )
        )
    return (
        "; ".join(dict.fromkeys(p for p in precondition_parts if p)) or None,
        steps,
        "; ".join(dict.fromkeys(technical)) or None,
    )


def _steps_from_observable(
    actions: list[str],
    observable: list[str],
    technical: str | None,
) -> list[CandidateStep]:
    if not observable:
        return []
    action_default = actions[0] if actions else STABLE_GENERIC_STEP
    steps: list[CandidateStep] = []
    for index, result in enumerate(observable):
        action = actions[index] if index < len(actions) else action_default
        steps.append(
            CandidateStep(
                step_number=index + 1,
                action=action,
                expected_result=result,
                test_data=technical if index == 0 else None,
            )
        )
    return steps


def _candidate(
    *,
    name: str,
    description: str,
    artifact_key: str,
    story_key: str | None,
    rn_filename: str,
    evidence: str,
    justification: str,
    body: str,
    extra_test_data: str | None,
    requires_condition: bool,
    existing: list[dict[str, str]],
    duplicate_of,
    classification: ScenarioClassification | None = None,
    user_action: str | None = None,
) -> GeneratedCaseCandidate | None:
    precondition, steps, technical = _steps_from_body(body)
    preserved = (user_action or "").strip()
    if classification and classification.qc_user_action and not preserved:
        preserved = classification.qc_user_action.strip()
    if preserved and not (is_user_action(preserved) or _USER_WHEN.search(preserved)):
        preserved = ""
    observable = list(classification.observable_then) if classification else []
    for clause in observable:
        extra = extract_technical(clause)
        if extra:
            technical = "; ".join(part for part in (technical, extra) if part)
    observable = [sanitize_user_text(clause) or clause for clause in observable]
    if observable:
        actions = [sanitize_user_text(step.action) or step.action for step in steps]
        if preserved:
            actions = [preserved for _ in actions] or [preserved]
        steps = _steps_from_observable(actions, observable, technical)
    if preserved:
        if not steps:
            steps = [
                CandidateStep(step_number=1, action=preserved, expected_result=observable[0] if observable else "")
            ]
        else:
            for step in steps:
                current = (step.action or "").strip()
                if not current or is_stable_generic_step(current) or not (
                    is_user_action(current) or _USER_WHEN.search(current)
                ):
                    step.action = preserved
    steps = [step for step in steps if (step.expected_result or "").strip()]
    if not steps:
        return None

    test_data_parts = [part for part in (technical, extra_test_data) if part]
    if classification:
        for note in classification.technical_notes:
            if note:
                test_data_parts.append(note)
    special = classification.special_condition if classification else None
    needs_config = bool(requires_condition) or bool(special) or bool(
        re.search(r"llave|configuraci[oó]n|flag|habilit", f"{precondition or ''} {body}", re.IGNORECASE)
    )
    pre_parts = [part for part in (precondition, special) if part]
    if needs_config and not pre_parts:
        pre_parts.append(
            "Requiere la configuración/condición descrita en Jira/RN; "
            "el caso es aplicable aunque no sea ejecutable aún."
        )
    precondition = "; ".join(dict.fromkeys(pre_parts)) or None
    expected = [step.expected_result for step in steps]
    functional_name = functional_title(name, expected)
    technical_heavy = bool(test_data_parts)
    return GeneratedCaseCandidate(
        name=functional_name[:250],
        description=description[:2000],
        precondition=precondition,
        requires_condition=needs_config,
        steps=steps,
        test_data="; ".join(test_data_parts) or None,
        related_functionality=(artifact_key or "").strip() or None,
        related_jira=(story_key or artifact_key or "").strip() or None,
        related_rn=rn_filename,
        evidence=evidence[:2000],
        justification=justification,
        possible_duplicate_of=duplicate_of(name, story_key or artifact_key, existing),
        confidence=classify_confidence(
            requires_condition=needs_config,
            basic_validation=False,
            steps=steps,
            technical_heavy=technical_heavy,
        ),
        review_required=True,
        basic_validation=False,
        priority=classify_priority(functional_name, steps, "; ".join(test_data_parts) or None),
        source_type="functionality",
    )


def _append_materialized(
    out: list[GeneratedCaseCandidate],
    candidate: GeneratedCaseCandidate | None,
    stats: GenerationStats,
    classification: ScenarioClassification,
) -> None:
    if candidate is None:
        return
    out.append(candidate)
    record_classification(stats, classification, candidate.name)


def _coverage_unit(
    *,
    coverage_id: str,
    clf: ScenarioClassification,
    title: str,
    body: str,
    evidence: str,
    epic_key: str,
    story_key: str,
    rn_filename: str,
    vocab: str,
    extra_test_data: str | None,
    requires_condition: bool,
    strategy: str,
    technical_group: str | None,
    condition_b: str | None,
    trace: str,
    user_action: str | None = None,
    source_origin: str = "gherkin",
) -> CoverageUnit:
    observables = list(clf.observable_then or clf.qc_observables or [])
    behavior = functional_title(title, observables or [title])
    intent = build_test_intent(title)
    unit_role: str = clf.role if clf.role in {"A", "G"} else "G"
    return CoverageUnit(
        coverage_id=coverage_id,
        role=unit_role,  # type: ignore[arg-type]
        behavior=behavior[:250],
        scenario=title,
        evidence=evidence[:2000],
        jira_key=story_key or epic_key,
        rn_key=epic_key or None,
        feature_story=story_key or epic_key,
        condition_b=condition_b,
        outline_strategy=strategy,
        technical_group=technical_group,
        traceability=trace,
        body=body,
        extra_test_data=extra_test_data,
        requires_condition=requires_condition,
        description=(vocab or title)[:2000],
        rn_filename=rn_filename,
        artifact_key=epic_key,
        story_key=story_key,
        observable_then=observables,
        technical_notes=list(clf.technical_notes or []),
        special_condition=clf.special_condition or clf.qc_condition,
        normal_precondition=clf.normal_precondition,
        test_intent=intent,
        qc_relevance=clf.qc_relevance,
        user_action=user_action,
        source_origin=source_origin,
    )


_SCROLL = re.compile(r"\bscroll\b", re.IGNORECASE)
_KEY_DEGRADATION = re.compile(
    r"no se logra obtener una llave|"
    r"la llave se encuentra vac[ií]a|"
    r"llave (inexistente|vac[ií]a|no se encuentra)",
    re.IGNORECASE,
)


def _is_coverable(clf: ScenarioClassification) -> bool:
    if clf.role in {"A", "G"}:
        return True
    if clf.qc_relevance in {"QC_FUNCTIONAL", "QC_REGRESSION"}:
        return True
    if clf.qc_relevance == "QC_VARIANT" and (clf.observable_then or clf.qc_observables):
        return True
    return False


def _collapse_matched(
    matched: list[tuple[dict[str, Any], ScenarioClassification]],
    extra_label: str,
) -> tuple[dict[str, Any], ScenarioClassification]:
    primary_block, primary_clf = matched[0]
    extras = [block["title"] for block, _clf in matched[1:] if block.get("title")]
    for _block, clf in matched[1:]:
        for obs in clf.observable_then or clf.qc_observables or []:
            if obs not in (primary_clf.observable_then or []):
                primary_clf.observable_then = list(primary_clf.observable_then or []) + [obs]
            if obs not in (primary_clf.qc_observables or []):
                primary_clf.qc_observables = list(primary_clf.qc_observables or []) + [obs]
    merged = dict(primary_block)
    if extras:
        merged["_qc_extra"] = extra_label + "; ".join(extras)
    return merged, primary_clf


def _merge_family(
    coverable: list[tuple[dict[str, Any], ScenarioClassification]],
    matcher: re.Pattern[str],
    extra_label: str,
) -> list[tuple[dict[str, Any], ScenarioClassification]]:
    if len(coverable) < 2:
        return coverable
    matched: list[tuple[dict[str, Any], ScenarioClassification]] = []
    rest: list[tuple[dict[str, Any], ScenarioClassification]] = []
    for block, clf in coverable:
        blob = f"{block.get('title') or ''}\n{block.get('body') or ''}"
        if matcher.search(blob):
            matched.append((block, clf))
        else:
            rest.append((block, clf))
    if len(matched) <= 1:
        return coverable
    return rest + [_collapse_matched(matched, extra_label)]


def _merge_scroll_family(
    coverable: list[tuple[dict[str, Any], ScenarioClassification]],
) -> list[tuple[dict[str, Any], ScenarioClassification]]:
    """One CoverageUnit for scroll + observable change; variants stay as test data."""
    return _merge_family(coverable, _SCROLL, "Variantes de scroll agrupadas: ")


def _merge_key_degradation_family(
    coverable: list[tuple[dict[str, Any], ScenarioClassification]],
) -> list[tuple[dict[str, Any], ScenarioClassification]]:
    """Same-story legend keys merge only when the functional observable matches."""
    from app.services.functional_equivalence import normalize_observable_text

    if len(coverable) < 2:
        return coverable
    matched: list[tuple[dict[str, Any], ScenarioClassification]] = []
    rest: list[tuple[dict[str, Any], ScenarioClassification]] = []
    for block, clf in coverable:
        blob = f"{block.get('title') or ''}\n{block.get('body') or ''}"
        if _KEY_DEGRADATION.search(blob):
            matched.append((block, clf))
        else:
            rest.append((block, clf))
    if len(matched) <= 1:
        return coverable
    buckets: dict[str, list[tuple[dict[str, Any], ScenarioClassification]]] = {}
    order: list[str] = []
    for block, clf in matched:
        obs = " ".join(clf.observable_then or clf.qc_observables or [block.get("title") or ""])
        key = normalize_observable_text(obs)
        if key not in buckets:
            order.append(key)
        buckets.setdefault(key, []).append((block, clf))
    out = list(rest)
    for key in order:
        group = buckets[key]
        if len(group) == 1:
            out.extend(group)
        else:
            out.append(
                _collapse_matched(group, "Variantes de leyenda/llave agrupadas: ")
            )
    return out


def _units_from_story_blocks(
    *,
    blocks: list[dict[str, Any]],
    story: dict[str, Any],
    epic_key: str,
    rn_filename: str,
    vocab: str,
    stats: GenerationStats,
    seq_holder: list[int],
) -> list[CoverageUnit]:
    units: list[CoverageUnit] = []
    story_key = story.get("key") or epic_key
    classified: list[tuple[dict[str, Any], ScenarioClassification]] = []
    support_notes: list[str] = []
    support_conditions: list[str] = []
    for block in blocks:
        clf = classify_scenario(block["title"], block["body"])
        origin = str(block.get("source_origin") or "gherkin")
        if (
            origin in {"ac", "description"}
            and not _is_coverable(clf)
            and _PROSE_UX.search(block.get("title") or "")
        ):
            clf = replace(
                clf,
                role="G",
                observable_then=list(clf.observable_then or [block["title"]]),
                qc_observables=list(clf.qc_observables or clf.observable_then or [block["title"]]),
                qc_relevance="QC_FUNCTIONAL",
            )
        then_ux = [
            clause
            for clause in (clf.then or [])
            if _INVENTORY_THEN_UX.search(clause) or _has_observable_consequence(clause)
        ]
        if then_ux and not clf.observable_then:
            clf = replace(
                clf,
                observable_then=then_ux,
                qc_observables=list(clf.qc_observables or then_ux),
            )
        if (
            then_ux
            and not _is_coverable(clf)
            and clf.role == "C"
            and (
                _pick_user_action(clf)
                or origin in {"ac", "description"}
                or _PROSE_UX.search(f"{block.get('title') or ''}\n{block.get('body') or ''}")
            )
        ):
            clf = replace(
                clf,
                role="G",
                observable_then=list(clf.observable_then or then_ux),
                qc_observables=list(clf.qc_observables or then_ux),
                qc_relevance="QC_FUNCTIONAL",
            )
        classified.append((block, clf))
        if _is_coverable(clf):
            continue
        record_classification(stats, clf, block["title"])
        if clf.role == "B" or clf.qc_relevance == "QC_VARIANT":
            if clf.special_condition:
                support_conditions.append(clf.special_condition)
            support_conditions.append(block["title"])
            support_notes.extend(clf.technical_notes or [])
        elif clf.qc_relevance == "IMPLEMENTATION_ONLY" or clf.role in {"D", "E", "F"}:
            support_notes.extend(clf.technical_notes or [block["title"]])

    if support_notes:
        stats.attached_support += 1
    condition_b = "; ".join(dict.fromkeys(support_conditions)) or None
    extra_support = "; ".join(dict.fromkeys(support_notes)) or None

    def _next_id() -> str:
        seq_holder[0] += 1
        return f"COV-{seq_holder[0]:03d}"

    coverable = [(block, clf) for block, clf in classified if _is_coverable(clf)]
    coverable = _merge_scroll_family(coverable)
    coverable = _merge_key_degradation_family(coverable)

    for block, clf in coverable:
        title = block["title"]
        body = block["body"]
        if block.get("_qc_extra"):
            extra_support = "; ".join(
                part for part in (extra_support, str(block["_qc_extra"])) if part
            )
        evidence = f"{story_key}: {title}\n{body[:1500]}"
        needs_story_condition = bool(support_conditions)
        examples = block["examples"] if block["outline"] else []
        strategy = example_strategy(examples) if examples else "single"
        trace = f"RN={epic_key}; Story={story_key}; Scenario={title}"
        source_origin = str(block.get("source_origin") or "gherkin")
        user_action = _pick_user_action(clf)
        noise = _non_qc_inventory_reason(title, body, user_action)
        if noise:
            stats.inventory_exclusions.append(f"{story_key}: {title}: {noise}")
            continue

        if strategy == "group" and examples:
            extra = format_examples(examples)
            tech_group = None
            if _examples_are_http_same_behavior(examples):
                codes = []
                for example in examples:
                    codes.extend(
                        value for value in example.values() if _HTTP_CODE.match(value.strip())
                    )
                tech_group = "HTTP " + ", ".join(dict.fromkeys(codes))
                extra = (
                    "Códigos HTTP explícitos en Examples (mismo comportamiento): "
                    + ", ".join(dict.fromkeys(codes))
                )
            extra = format_examples(examples)
            units.append(
                _coverage_unit(
                    coverage_id=_next_id(),
                    clf=clf,
                    title=title,
                    body=body,
                    evidence=evidence,
                    epic_key=epic_key,
                    story_key=story_key,
                    rn_filename=rn_filename,
                    vocab=vocab,
                    extra_test_data="; ".join(part for part in (extra, extra_support) if part) or None,
                    requires_condition=needs_story_condition,
                    strategy=strategy,
                    technical_group=tech_group,
                    condition_b=condition_b,
                    trace=trace,
                    user_action=user_action,
                    source_origin=source_origin,
                )
            )
            continue

        if strategy == "group_by_outcome" and examples:
            for outcome, group in group_examples_by_outcome(examples).items():
                extra = format_examples(group)
                units.append(
                    _coverage_unit(
                        coverage_id=_next_id(),
                        clf=clf,
                        title=f"{title} ({outcome})"[:250],
                        body=body,
                        evidence=evidence + "\n" + extra,
                        epic_key=epic_key,
                        story_key=story_key,
                        rn_filename=rn_filename,
                        vocab=vocab,
                        extra_test_data="; ".join(part for part in (extra, extra_support) if part) or None,
                        requires_condition=needs_story_condition,
                        strategy=strategy,
                        technical_group=f"outcome:{outcome}",
                        condition_b=condition_b,
                        trace=trace + f"; outcome={outcome}",
                        user_action=user_action,
                        source_origin=source_origin,
                    )
                )
            continue

        if strategy == "split_functional" and examples:
            for example in examples:
                label = ", ".join(f"{k}={v}" for k, v in example.items() if v)
                extra = "Example funcional explícito: " + label
                units.append(
                    _coverage_unit(
                        coverage_id=_next_id(),
                        clf=clf,
                        title=f"{title} ({label})"[:250],
                        body=body,
                        evidence=evidence + "\n" + label,
                        epic_key=epic_key,
                        story_key=story_key,
                        rn_filename=rn_filename,
                        vocab=vocab,
                        extra_test_data="; ".join(part for part in (extra, extra_support) if part) or None,
                        requires_condition=needs_story_condition,
                        strategy=strategy,
                        technical_group=None,
                        condition_b=condition_b,
                        trace=trace + f"; example={label}",
                        user_action=user_action,
                        source_origin=source_origin,
                    )
                )
            continue

        then_generic = (not clf.then) or all(_is_generic_then(clause) for clause in clf.then)
        then_atoms = [
            clause
            for clause in (clf.then or [])
            if _has_observable_consequence(clause) or _INVENTORY_THEN_UX.search(clause)
        ]
        satellites = [
            item for item in then_atoms if _is_satellite_observable(item) or _http_or_api_only(item)
        ]
        primary = [item for item in then_atoms if item not in satellites]
        extra_notes = extra_support
        if satellites:
            extra_notes = "; ".join(part for part in (extra_notes, *satellites) if part)
        should_atomize = bool(user_action) and (not then_generic) and len(primary) > 1
        if _SCROLL.search(f"{title}\n{body}"):
            should_atomize = False
        if not should_atomize:
            units.append(
                _coverage_unit(
                    coverage_id=_next_id(),
                    clf=clf,
                    title=title,
                    body=body,
                    evidence=evidence,
                    epic_key=epic_key,
                    story_key=story_key,
                    rn_filename=rn_filename,
                    vocab=vocab,
                    extra_test_data=extra_notes or extra_support,
                    requires_condition=needs_story_condition,
                    strategy=strategy,
                    technical_group=None,
                    condition_b=condition_b,
                    trace=trace,
                    user_action=user_action,
                    source_origin=source_origin,
                )
            )
            continue
        for group in _group_observable_atoms(primary):
            obs = [item for item in group if item]
            if not obs:
                continue
            atom_clf = replace(clf, observable_then=obs, qc_observables=obs)
            units.append(
                _coverage_unit(
                    coverage_id=_next_id(),
                    clf=atom_clf,
                    title=title,
                    body=_focused_body(list(clf.given or []), user_action, "; ".join(obs)),
                    evidence=evidence,
                    epic_key=epic_key,
                    story_key=story_key,
                    rn_filename=rn_filename,
                    vocab=vocab,
                    extra_test_data=extra_notes,
                    requires_condition=needs_story_condition,
                    strategy=strategy,
                    technical_group=None,
                    condition_b=condition_b,
                    trace=f"{trace}; then={obs[0][:120]}",
                    user_action=user_action,
                    source_origin=source_origin,
                )
            )
    return units


def build_coverage_inventory(
    artifacts: list[dict[str, Any]],
    rn_filename: str,
    stats: GenerationStats | None = None,
) -> list[CoverageUnit]:
    """A/G coverage units from Jira Gherkin. Not Test Cases."""
    stats = stats or GenerationStats()
    units: list[CoverageUnit] = []
    seq_holder = [0]
    for artifact in artifacts:
        epic_key = artifact.get("key") or ""
        children = list(artifact.get("children") or [])
        sources = children or [artifact]
        seen_blocks: set[str] = set()
        gherkin_corpus: list[str] = []
        added_before = len(units)

        def _consume(story: dict[str, Any]) -> None:
            ac = story.get("acceptance_criteria") or ""
            blocks = extract_gherkin_blocks(story.get("description") or "", ac)
            unique: list[dict[str, Any]] = []
            for block in blocks:
                key = _block_dedupe_key(block)
                gherkin_corpus.append(f"{block.get('title') or ''} {block.get('body') or ''}")
                if key in seen_blocks:
                    continue
                seen_blocks.add(key)
                unique.append(block)
            gherkin_blob = re.sub(r"\s+", " ", " ".join(gherkin_corpus).lower())
            for block in extract_prose_observable_blocks(
                story.get("description") or "",
                ac,
                stats,
                story_key=str(story.get("key") or epic_key),
            ):
                key = _block_dedupe_key(block)
                if key in seen_blocks:
                    continue
                snippet = re.sub(r"\s+", " ", (block.get("title") or "").lower())
                if snippet and gherkin_blob and snippet in gherkin_blob:
                    continue
                seen_blocks.add(key)
                unique.append(block)
            if not unique:
                stats.inventory_exclusions.append(
                    f"{story.get('key') or epic_key}: sin Gherkin ni comportamiento "
                    "observable en AC/descripción"
                )
                return
            vocab = (ac or artifact.get("acceptance_criteria") or "").strip()
            units.extend(
                _units_from_story_blocks(
                    blocks=unique,
                    story=story,
                    epic_key=epic_key,
                    rn_filename=rn_filename,
                    vocab=vocab,
                    stats=stats,
                    seq_holder=seq_holder,
                )
            )

        for story in sources:
            _consume(story)
        if children:
            _consume(artifact)
        start = added_before
        kept_prefix = units[:start]
        units[:] = kept_prefix + _dedupe_inventory_units(units[start:])
    return units


def materialize_coverage_units(
    units: list[CoverageUnit],
    existing: list[dict[str, str]],
    duplicate_of,
    stats: GenerationStats | None = None,
) -> list[GeneratedCaseCandidate]:
    stats = stats or GenerationStats()
    out: list[GeneratedCaseCandidate] = []
    for unit in units:
        clf = ScenarioClassification(
            role=unit.role,
            observable_then=list(unit.observable_then),
            technical_notes=list(unit.technical_notes),
            special_condition=unit.special_condition,
            normal_precondition=unit.normal_precondition,
        )
        candidate = _candidate(
            name=unit.scenario,
            description=unit.description or unit.behavior,
            artifact_key=unit.artifact_key,
            story_key=unit.story_key,
            rn_filename=unit.rn_filename,
            evidence=unit.evidence,
            justification=(
                "Materialización determinista de CoverageUnit "
                f"{unit.coverage_id} ({unit.role})."
            ),
            body=unit.body,
            extra_test_data=unit.extra_test_data,
            requires_condition=unit.requires_condition,
            existing=existing,
            duplicate_of=duplicate_of,
            classification=clf,
            user_action=unit.user_action,
        )
        if candidate is None:
            continue
        candidate.covers = [unit.coverage_id]
        candidate.review_required = True
        _append_materialized(out, candidate, stats, clf)
    return out


def candidates_from_jira_artifacts(
    artifacts: list[dict[str, Any]],
    rn_filename: str,
    existing: list[dict[str, str]],
    duplicate_of,
    stats: GenerationStats | None = None,
) -> list[GeneratedCaseCandidate]:
    stats = stats or GenerationStats()
    units = build_coverage_inventory(artifacts, rn_filename, stats=stats)
    out = materialize_coverage_units(units, existing, duplicate_of, stats=stats)
    out = apply_qc_rules(out, stats=stats)
    return apply_executability_gate(out, units)
