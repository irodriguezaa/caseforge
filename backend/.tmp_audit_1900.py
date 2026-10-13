"""Audit WEBCL-1900 generation pipeline. Print-only; no writes."""

from __future__ import annotations

from collections import defaultdict

from app.schemas.case_generation import GenerationStats
from app.services.gherkin_coverage import (
    build_coverage_inventory,
    extract_gherkin_blocks,
    extract_prose_observable_blocks,
    materialize_coverage_units,
)
from app.services.jira_generation import fetch_artifacts_for_keys
from app.services.qc_candidate_rules import apply_qc_rules
from app.services.scenario_classifier import classify_scenario


def _clip(text: str, n: int = 240) -> str:
    raw = (text or "").replace("\n", " ").strip()
    return raw if len(raw) <= n else raw[: n - 1] + "…"


def main() -> None:
    arts = fetch_artifacts_for_keys(["WEBCL-1900"])
    if not arts:
        print("NO_JIRA_ARTIFACTS")
        return
    epic = arts[0]
    print("=== EPIC ===")
    print("key", epic.get("key"), "type", epic.get("issuetype"), "summary", epic.get("summary"))
    print("AC", _clip(epic.get("acceptance_criteria") or "", 800))
    print("DESC", _clip(epic.get("description") or "", 400))
    print("children", epic.get("child_count"), "feature_children", epic.get("feature_child_count"))
    print()
    for child in epic.get("children") or []:
        print("=== STORY", child.get("key"), child.get("issuetype"), "===")
        print("summary", child.get("summary"))
        print("AC", _clip(child.get("acceptance_criteria") or "", 500) or "(empty)")
        desc = child.get("description") or ""
        print("DESC_LEN", len(desc))
        print("DESC_HEAD", _clip(desc, 500))
        blocks = extract_gherkin_blocks(desc, child.get("acceptance_criteria") or "")
        print("GHERKIN_BLOCKS", len(blocks))
        for block in blocks:
            clf = classify_scenario(block["title"], block["body"])
            print(
                "  SCENARIO",
                block.get("title"),
                "| role",
                clf.role,
                "| qc",
                clf.qc_relevance,
                "| reason",
                _clip(clf.reason or "", 160),
            )
            print("    when", clf.when or clf.qc_user_action)
            print("    then", (clf.observable_then or clf.then or [])[:3])
            print("    body", _clip(block.get("body") or "", 280))
        prose_stats = GenerationStats()
        prose = extract_prose_observable_blocks(
            desc,
            child.get("acceptance_criteria") or "",
            prose_stats,
            story_key=str(child.get("key")),
        )
        print("PROSE_BLOCKS", len(prose), "excl", prose_stats.inventory_exclusions[:8])
        print()

    epic_stats = GenerationStats()
    epic_prose = extract_prose_observable_blocks(
        epic.get("description") or "",
        epic.get("acceptance_criteria") or "",
        epic_stats,
        story_key="WEBCL-1900",
    )
    print("=== EPIC PROSE ===", len(epic_prose))
    for block in epic_prose:
        print(" ", block.get("title"))
    print("epic excl", epic_stats.inventory_exclusions)

    stats = GenerationStats()
    units = build_coverage_inventory(arts, "web17.pdf", stats=stats)
    print("\n=== INVENTORY", len(units), "===")
    print("exclusions:")
    for row in stats.inventory_exclusions:
        print(" ", row)
    for unit in units:
        print(
            unit.coverage_id,
            unit.source_origin,
            unit.story_key,
            "|",
            unit.scenario,
            "| action=",
            unit.user_action,
            "| then=",
            unit.observable_then,
        )

    dets = materialize_coverage_units(units, [], lambda *_a: None, stats=stats)
    dets = apply_qc_rules(dets, stats=stats)
    print("\n=== MATERIALIZED", len(dets), "===")
    for cand in dets:
        action = cand.steps[0].action if cand.steps else ""
        expected = cand.steps[0].expected_result if cand.steps else ""
        print(
            cand.name,
            "| covers",
            cand.covers,
            "| origin",
            cand.generation_origin,
            "| A=",
            action,
            "| E=",
            expected,
        )


if __name__ == "__main__":
    main()
