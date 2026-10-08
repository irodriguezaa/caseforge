"""RN EPC scope contract: RN is membership, TCs are the result."""

from types import SimpleNamespace

from app.schemas.case_generation import CandidateStep, CoverageUnit, GeneratedCaseCandidate
from app.services.ai_case_engine import _keep_llm_functionality_candidates
from app.services.rn_epc_scope import (
    ORPHAN_EPC,
    build_rn_scope_coverage,
    case_scope_key,
    coverage_status,
    left_join_epic_progress,
    remap_case_fields,
    rn_keys_from_normalized,
    stamp_candidate_identity,
    story_to_rn_map,
)
from app.services.test_case_export import epic_progress_rows


IOS_RN = [
    "IOSPR-1435",
    "IOSPR-1433",
    "IOSPR-1365",
    "IOSPR-1348",
    "IOSPR-1335",
    "IOSPR-1310",
]


def _artifacts() -> list[dict]:
    return [
        {
            "key": "IOSPR-1365",
            "children": [
                {"key": "IOSPR-1366", "parent_key": "IOSPR-1365", "issuetype": "Technical Story"},
                {"key": "IOSPR-1432", "parent_key": "IOSPR-1365", "issuetype": "Technical Story"},
            ],
        },
        {
            "key": "IOSPR-1335",
            "children": [
                {"key": "IOSPR-1336", "parent_key": "IOSPR-1335", "issuetype": "Technical Story"},
                {"key": "IOSPR-1337", "parent_key": "IOSPR-1335", "issuetype": "Technical Story"},
                {"key": "IOSPR-1338", "parent_key": "IOSPR-1335", "issuetype": "Technical Story"},
            ],
        },
        {
            "key": "IOSPR-1348",
            "children": [{"key": "IOSPR-1349", "parent_key": "IOSPR-1348", "issuetype": "Technical Story"}],
        },
        {"key": "IOSPR-1435", "children": [{"key": "IOSPR-1436", "parent_key": "IOSPR-1435"}]},
        {"key": "IOSPR-1433", "children": [{"key": "IOSPR-1434", "parent_key": "IOSPR-1433"}]},
        {"key": "IOSPR-1310", "children": [{"key": "IOSPR-1311", "parent_key": "IOSPR-1310"}]},
    ]


def _candidate(*, func: str | None, jira: str | None = None, covers: list[str] | None = None) -> GeneratedCaseCandidate:
    return GeneratedCaseCandidate(
        name="Caso",
        description="Caso",
        steps=[CandidateStep(step_number=1, action="El usuario abre", expected_result="Se muestra el resultado")],
        related_functionality=func,
        related_jira=jira,
        evidence="e",
        justification="j",
        covers=covers or ["COV-001"],
    )


def _case(**kwargs):
    defaults = {
        "component": None,
        "technical_epic": None,
        "hn_source": None,
        "technical_story": None,
        "status": "UNEXECUTED",
        "estimation_hours": 0.2,
        "test_case_id": "QC-001",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_rn_keys_from_normalized_preserve_ios_spine() -> None:
    raw = {"normalized": {"technical_epics": [{"id": key} for key in IOS_RN]}}
    assert rn_keys_from_normalized(raw) == IOS_RN


def test_zero_tc_epics_remain_on_spine() -> None:
    rows = left_join_epic_progress(rn_keys=IOS_RN, cases=[], story_map=story_to_rn_map(_artifacts(), IOS_RN))
    assert [row["key"] for row in rows] == IOS_RN
    for key in ("IOSPR-1310", "IOSPR-1433", "IOSPR-1435"):
        row = next(item for item in rows if item["key"] == key)
        assert row["total"] == 0
        assert row["hours"] == 0
        assert row["percent"] == 0
        assert row["estado"] in {"sin_casos", "sin_gherkin"}


def test_story_1366_is_not_an_independent_epc() -> None:
    mapping = story_to_rn_map(_artifacts(), IOS_RN)
    rows = left_join_epic_progress(
        rn_keys=IOS_RN,
        cases=[_case(technical_epic="IOSPR-1366", technical_story="IOSPR-1366")],
        story_map=mapping,
    )
    keys = [row["key"] for row in rows]
    assert "IOSPR-1366" not in keys
    assert "IOSPR-1349" not in keys
    assert "IOSPR-1336" not in keys
    epic = next(item for item in rows if item["key"] == "IOSPR-1365")
    assert epic["total"] == 1


def test_stamp_story_becomes_rn_epic() -> None:
    mapping = story_to_rn_map(_artifacts(), IOS_RN)
    stamped = stamp_candidate_identity(
        _candidate(func="IOSPR-1366", jira="IOSPR-1366"),
        IOS_RN,
        mapping,
    )
    assert stamped.related_functionality == "IOSPR-1365"
    assert stamped.related_jira == "IOSPR-1366"


def test_stamp_1335_stories_stay_under_epic() -> None:
    mapping = story_to_rn_map(_artifacts(), IOS_RN)
    for story in ("IOSPR-1336", "IOSPR-1337", "IOSPR-1338"):
        stamped = stamp_candidate_identity(_candidate(func=story, jira=story), IOS_RN, mapping)
        assert stamped.related_functionality == "IOSPR-1335"
        assert stamped.related_jira == story


def test_related_functionality_never_keeps_child_story() -> None:
    mapping = story_to_rn_map(_artifacts(), IOS_RN)
    stamped = stamp_candidate_identity(
        _candidate(func="IOSPR-1349", jira="IOSPR-1349"),
        IOS_RN,
        mapping,
    )
    assert stamped.related_functionality == "IOSPR-1348"
    assert "IOSPR-1349" not in (stamped.related_functionality or "")


def test_excel_left_join_keeps_zero_tc_rows() -> None:
    cases = [
        _case(technical_epic="IOSPR-1365", status="PASS", test_case_id="QC-001"),
        _case(technical_epic="IOSPR-1335", status="UNEXECUTED", test_case_id="QC-002"),
    ]
    rows = epic_progress_rows(cases, scope_keys=IOS_RN, coverage={"story_to_epic": story_to_rn_map(_artifacts(), IOS_RN)})
    assert [row["key"] for row in rows] == IOS_RN
    by_key = {row["key"]: row for row in rows}
    assert by_key["IOSPR-1310"]["total"] == 0
    assert by_key["IOSPR-1435"]["hours"] == 0
    assert by_key["IOSPR-1365"]["total"] == 1
    assert "IOSPR-1366" not in by_key


def test_orphan_is_not_invented_as_rn_epc() -> None:
    mapping = story_to_rn_map(_artifacts(), IOS_RN)
    rows = left_join_epic_progress(
        rn_keys=IOS_RN,
        cases=[_case(technical_epic="ZZZZ-999", component="ZZZZ-999")],
        story_map=mapping,
    )
    keys = [row["key"] for row in rows]
    assert keys[:6] == IOS_RN
    assert "ZZZZ-999" not in keys
    orphan = next(item for item in rows if item["key"] == ORPHAN_EPC)
    assert orphan["orphan"] is True
    assert orphan["total"] == 1
    assert case_scope_key(
        technical_epic="ZZZZ-999",
        component="ZZZZ-999",
        hn_source=None,
        technical_story=None,
        rn_keys=IOS_RN,
        story_map=mapping,
    ) is None


def test_remap_only_when_parent_in_rn_scope() -> None:
    mapping = story_to_rn_map(_artifacts(), IOS_RN)
    hit = remap_case_fields(
        technical_epic="IOSPR-1366",
        technical_story=None,
        component="IOSPR-1366",
        rn_keys=IOS_RN,
        story_map=mapping,
        justification="orig",
    )
    assert hit is not None
    assert hit["technical_epic"] == "IOSPR-1365"
    assert "IOSPR-1366" in (hit["technical_story"] or "")
    assert "Remap EPC" in (hit["justification"] or "")
    miss = remap_case_fields(
        technical_epic="OTHER-1",
        technical_story=None,
        component="OTHER-1",
        rn_keys=IOS_RN,
        story_map={"OTHER-1": "OTHER-PARENT"},
        justification="",
    )
    assert miss is None


def test_coverage_status_rules() -> None:
    assert coverage_status(ag_total=0, ag_covered=0, tc_count=0) == "sin_gherkin"
    assert coverage_status(ag_total=3, ag_covered=0, tc_count=0) == "sin_casos"
    assert coverage_status(ag_total=3, ag_covered=1, tc_count=2) == "parcial"
    assert coverage_status(ag_total=3, ag_covered=3, tc_count=2) == "cubierta"


def test_snapshot_includes_zero_tc_epics() -> None:
    inventory = [
        CoverageUnit(
            coverage_id="COV-001",
            role="A",
            behavior="x",
            scenario="x",
            evidence="e",
            jira_key="IOSPR-1336",
            rn_key="IOSPR-1335",
            artifact_key="IOSPR-1335",
            story_key="IOSPR-1336",
        )
    ]
    candidates = [
        stamp_candidate_identity(
            _candidate(func="IOSPR-1336", jira="IOSPR-1336", covers=["COV-001"]),
            IOS_RN,
            story_to_rn_map(_artifacts(), IOS_RN),
        )
    ]
    snap = build_rn_scope_coverage(
        rn_keys=IOS_RN,
        artifacts=_artifacts(),
        inventory=inventory,
        covered_ids=["COV-001"],
        candidates=candidates,
    )
    assert [row["rn_key"] for row in snap["epics"]] == IOS_RN
    by_key = {row["rn_key"]: row for row in snap["epics"]}
    assert by_key["IOSPR-1310"]["test_cases"] == 0
    assert by_key["IOSPR-1310"]["estado"] == "sin_gherkin"
    assert by_key["IOSPR-1335"]["test_cases"] == 1
    assert by_key["IOSPR-1335"]["estado"] == "cubierta"
    assert "IOSPR-1366" not in by_key
    assert snap["story_to_epic"]["IOSPR-1366"] == "IOSPR-1365"


def test_llm_keep_remaps_story_functionality_to_rn_epic() -> None:
    units = [
        CoverageUnit(
            coverage_id="COV-001",
            role="A",
            behavior="Menu",
            scenario="Menu",
            evidence="e",
            jira_key="IOSPR-1366",
            rn_key="IOSPR-1365",
            artifact_key="IOSPR-1365",
            story_key="IOSPR-1366",
        )
    ]
    kept = _keep_llm_functionality_candidates(
        [_candidate(func="IOSPR-1366", jira="IOSPR-1366")],
        {"IOSPR-1365", "IOSPR-1366"},
        {"COV-001"},
        inventory=units,
        artifacts=_artifacts(),
        tickets={"functionality": [(key, key) for key in IOS_RN]},
    )
    assert len(kept) == 1
    assert kept[0].related_functionality == "IOSPR-1365"
    assert kept[0].related_jira == "IOSPR-1366"
