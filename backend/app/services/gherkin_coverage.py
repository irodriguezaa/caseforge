"""Evidence-backed scenario materialization from Jira Gherkin.

Does not invent scenarios. Scenario Outline Examples that are only HTTP codes with no
evidenced UX difference are grouped (HANDOFF). Distinct example values that are not
HTTP-only are materialized as independent functional conditions.
"""

from __future__ import annotations

import re
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
    classify_scenario,
    record_classification,
)

_SCENARIO_SPLIT = re.compile(
    r"^\s*(Scenario Outline|Scenario|Escenario esquemático|Escenario)\s*:\s*(.+?)\s*$",
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
            blocks.append(block)
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
        scenario_body = re.split(r"^\s*Examples\s*:\s*$", body, maxsplit=1, flags=re.IGNORECASE | re.MULTILINE)[0]
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
    parts = re.split(r"^\s*Examples\s*:\s*$", body, maxsplit=1, flags=re.IGNORECASE | re.MULTILINE)
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
    if not actions:
        actions = [STABLE_GENERIC_STEP]
    steps: list[CandidateStep] = []
    if not expected:
        return (
            "; ".join(dict.fromkeys(p for p in precondition_parts if p)) or None,
            steps,
            "; ".join(dict.fromkeys(technical)) or None,
        )
    count = max(len(expected), 1)
    user_action = actions[0] if actions else STABLE_GENERIC_STEP
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
) -> GeneratedCaseCandidate | None:
    precondition, steps, technical = _steps_from_body(body)
    observable = list(classification.observable_then) if classification else []
    for clause in observable:
        extra = extract_technical(clause)
        if extra:
            technical = "; ".join(part for part in (technical, extra) if part)
    observable = [sanitize_user_text(clause) or clause for clause in observable]
    if observable:
        actions = [sanitize_user_text(step.action) or step.action for step in steps]
        steps = _steps_from_observable(actions, observable, technical)
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
    return rest + [(merged, primary_clf)]


def _merge_scroll_family(
    coverable: list[tuple[dict[str, Any], ScenarioClassification]],
) -> list[tuple[dict[str, Any], ScenarioClassification]]:
    """One CoverageUnit for scroll + observable change; variants stay as test data."""
    return _merge_family(coverable, _SCROLL, "Variantes de scroll agrupadas: ")


def _merge_key_degradation_family(
    coverable: list[tuple[dict[str, Any], ScenarioClassification]],
) -> list[tuple[dict[str, Any], ScenarioClassification]]:
    """Missing and empty copy keys are one negative/variant CoverageUnit."""
    return _merge_family(coverable, _KEY_DEGRADATION, "Variantes de leyenda/llave agrupadas: ")


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
                    )
                )
            continue

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
                extra_test_data=extra_support,
                requires_condition=needs_story_condition,
                strategy=strategy,
                technical_group=None,
                condition_b=condition_b,
                trace=trace,
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
        added_before = len(units)

        def _consume(story: dict[str, Any]) -> None:
            ac = story.get("acceptance_criteria") or ""
            blocks = extract_gherkin_blocks(story.get("description") or "", ac)
            unique: list[dict[str, Any]] = []
            for block in blocks:
                key = _block_dedupe_key(block)
                if key in seen_blocks:
                    continue
                seen_blocks.add(key)
                unique.append(block)
            if not unique:
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
        if len(units) == added_before and children:
            _consume(artifact)
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
