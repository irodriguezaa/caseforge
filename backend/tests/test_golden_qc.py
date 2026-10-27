"""Generate the four golden EPCs and compare the Excel against aaf_legacy_release47.json."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.schemas.case_generation import GenerationStats
from app.services.case_persistence import next_test_case_id
from app.services.gherkin_coverage import candidates_from_jira_artifacts
from app.services.test_case_export import build_test_cases_workbook
from tests.golden.compare_golden import compare
from tests.golden.epics import GOLDEN_EPC_KEYS, load_jira_artifacts

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
GOLDEN_JSON = GOLDEN_DIR / "aaf_legacy_release47.json"


def _cases_and_ledger():
    artifacts = load_jira_artifacts()
    stats = GenerationStats()
    candidates = candidates_from_jira_artifacts(
        artifacts, "golden.pdf", [], lambda *_a: None, stats=stats
    )
    used: list[str] = []
    cases = []
    name_to_id: dict[str, str] = {}
    for candidate in candidates:
        if not candidate.steps:
            continue
        label = next_test_case_id(used)
        used.append(label)
        name_to_id[candidate.name] = label
        cases.append(
            SimpleNamespace(
                test_case_id=label,
                test_case_name=candidate.name,
                component=(candidate.related_functionality or "")[:150],
                technical_epic=candidate.related_functionality,
                hn_source=None,
                status="UNEXECUTED",
                estimation_hours=0.2,
                priority=candidate.priority or "CRITICAL",
                test_type="FUNCTIONAL",
                source_type="functionality",
                user_type=None,
                test_data=candidate.test_data,
                evidence=candidate.evidence,
                justification=candidate.justification,
                technical_story=candidate.related_jira,
                scenario_origin=None,
                confidence=candidate.confidence,
                complexity=None,
                description=candidate.description,
                device=None,
                steps=[
                    SimpleNamespace(
                        step_number=step.step_number,
                        test_step=step.action,
                        expected_result=step.expected_result,
                    )
                    for step in candidate.steps
                ],
            )
        )
    for row in stats.scenario_ledger:
        ref = str(row.get("case_id") or "")
        if ref in name_to_id:
            row["case_id"] = name_to_id[ref]
    return cases, stats.scenario_ledger


def test_golden_aaf_legacy_release47(tmp_path, capsys) -> None:
    cases, ledger = _cases_and_ledger()
    payload = build_test_cases_workbook(
        cases,
        scope_keys=list(GOLDEN_EPC_KEYS),
        scenario_ledger=ledger,
    )
    excel_path = tmp_path / "golden_aaf.xlsx"
    excel_path.write_bytes(payload)
    result = compare(GOLDEN_JSON, excel_path)
    print(result["report"])
    assert result["ok"], result["report"]
