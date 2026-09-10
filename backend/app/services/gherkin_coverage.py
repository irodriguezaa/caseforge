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
_GIVEN = re.compile(r"^\s*(Given|Dado que|Dado|And|Y|Pero|But)\s+", re.IGNORECASE)
_WHEN = re.compile(r"^\s*(When|Cuando)\s+", re.IGNORECASE)
_THEN = re.compile(r"^\s*(Then|Entonces)\s+", re.IGNORECASE)
_TECHNICAL = re.compile(
    r"\b(GET|POST|PUT|PATCH|DELETE)\b|"
    r"https?://\S+|"
    r"/services/[^\s]+|"
    r"/[a-z]+/v\d+/[^\s]+|"
    r"\bstatus codes?\b|"
    r"\bHTTP\b|"
    r"\binvoca\b|"
    r"module_version|"
    r"""["'][A-Za-z_][A-Za-z0-9_]*["']""",
    re.IGNORECASE,
)


def sanitize_user_text(text: str) -> str:
    cleaned = _TECHNICAL.sub(" ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" :;-")
    return cleaned


def extract_technical(text: str) -> str:
    found = [match.group(0) for match in _TECHNICAL.finditer(text)]
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
    precondition_parts: list[str] = []
    actions: list[str] = []
    expected: list[str] = []
    technical: list[str] = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("|"):
            continue
        tech = extract_technical(line)
        if tech:
            technical.append(tech)
        if _WHEN.match(line):
            text = sanitize_user_text(_WHEN.sub("", line))
            if text:
                actions.append(text)
        elif _THEN.match(line):
            text = sanitize_user_text(_THEN.sub("", line))
            if text:
                expected.append(text)
        elif _GIVEN.match(line):
            text = sanitize_user_text(_GIVEN.sub("", line))
            if text:
                precondition_parts.append(text)
    steps: list[CandidateStep] = []
    if not actions and not expected:
        return (
            "; ".join(precondition_parts) or None,
            steps,
            "; ".join(dict.fromkeys(technical)) or None,
        )
    count = max(len(actions), len(expected), 1)
    for index in range(count):
        action = actions[index] if index < len(actions) else actions[-1] if actions else "El usuario continúa el flujo."
        result = expected[index] if index < len(expected) else expected[-1] if expected else ""
        steps.append(
            CandidateStep(
                step_number=index + 1,
                action=action,
                expected_result=result,
            )
        )
    return (
        "; ".join(precondition_parts) or None,
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
    action_default = actions[0] if actions else "El usuario recorre el flujo descrito en el escenario."
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
    if observable and (
        not steps
        or any(not (step.expected_result or "").strip() for step in steps)
    ):
        actions = [step.action for step in steps]
        steps = _steps_from_observable(actions, observable, technical)
    elif observable and steps:
        for index, result in enumerate(observable):
            if index < len(steps):
                steps[index].expected_result = result
    steps = [step for step in steps if (step.expected_result or "").strip()]
    if not steps:
        return None

    test_data_parts = [part for part in (technical, extra_test_data) if part]
    if classification:
        for note in classification.technical_notes:
            if note:
                test_data_parts.append(note)
    special = classification.special_condition if classification else None
    normal = classification.normal_precondition if classification else None
    needs_config = requires_condition or bool(special)
    if not needs_config:
        needs_config = bool(
            re.search(r"llave|configuraci[oó]n|flag|habilit", f"{name} {body}", re.IGNORECASE)
        )
        if needs_config:
            special = special or (
                "Condición especial descrita en Jira (flag, configuración u operación)."
            )
    pre_parts = [part for part in (normal, precondition) if part]
    if special:
        pre_parts.append(f"Condición especial: {special}")
    elif needs_config and not pre_parts:
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
        related_functionality=artifact_key,
        related_jira=story_key or artifact_key,
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
    behavior = functional_title(title, clf.observable_then or [title])
    return CoverageUnit(
        coverage_id=coverage_id,
        role=clf.role if clf.role in {"A", "G"} else "A",
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
        observable_then=list(clf.observable_then or []),
        technical_notes=list(clf.technical_notes or []),
        special_condition=clf.special_condition,
        normal_precondition=clf.normal_precondition,
    )


def build_coverage_inventory(
    artifacts: list[dict[str, Any]],
    rn_filename: str,
    stats: GenerationStats | None = None,
) -> list[CoverageUnit]:
    """A/G coverage units from Jira Gherkin. Not Test Cases."""
    stats = stats or GenerationStats()
    units: list[CoverageUnit] = []
    seq = 0
    for artifact in artifacts:
        epic_key = artifact.get("key") or ""
        sources = artifact.get("children") or []
        if not sources:
            sources = [artifact]
        for story in sources:
            story_key = story.get("key") or epic_key
            description = story.get("description") or ""
            ac = story.get("acceptance_criteria") or artifact.get("acceptance_criteria") or ""
            combined = gherkin_source_text(description)
            blocks = parse_gherkin_blocks(combined)
            if not blocks:
                continue
            vocab = ac.strip()
            classified: list[tuple[dict[str, Any], ScenarioClassification]] = []
            support_notes: list[str] = []
            support_conditions: list[str] = []
            for block in blocks:
                clf = classify_scenario(block["title"], block["body"])
                classified.append((block, clf))
                if clf.role in {"B", "C"}:
                    record_classification(stats, clf, block["title"])
                    support_notes.extend(clf.technical_notes or [block["title"]])
                    if clf.special_condition:
                        support_conditions.append(clf.special_condition)
                    elif clf.role == "B":
                        support_conditions.append(block["title"])
                elif clf.role in {"D", "E", "F"}:
                    record_classification(stats, clf, block["title"])

            if support_notes:
                stats.attached_support += 1
            condition_b = "; ".join(dict.fromkeys(support_conditions)) or None
            extra_support = "; ".join(dict.fromkeys(support_notes)) or None

            for block, clf in classified:
                if clf.role not in {"A", "G"}:
                    continue
                title = block["title"]
                body = block["body"]
                evidence = f"{story_key}: {title}\n{body[:1500]}"
                needs_story_condition = bool(support_conditions)
                if needs_story_condition and not clf.special_condition:
                    clf.special_condition = condition_b
                examples = block["examples"] if block["outline"] else []
                strategy = example_strategy(examples) if examples else "single"
                trace = f"RN={epic_key}; Story={story_key}; Scenario={title}"

                def _next_id() -> str:
                    nonlocal seq
                    seq += 1
                    return f"COV-{seq:03d}"

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
                    extra = "; ".join(part for part in (extra, extra_support) if part)
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
                            extra_test_data=extra,
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
                        extra = "; ".join(
                            part for part in (format_examples(group), extra_support) if part
                        )
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
                                extra_test_data=extra,
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
                        extra = "; ".join(
                            part
                            for part in ("Example funcional explícito: " + label, extra_support)
                            if part
                        )
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
                                extra_test_data=extra,
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
    return apply_qc_rules(out, stats=stats)
