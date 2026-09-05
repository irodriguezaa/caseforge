"""Zephyr publication mapping dry-run. No Jira/Zephyr writes."""

from app.models.test_case import TestCase, TestCasePriority, TestCaseStatus, TestCaseType
from app.models.test_step import TestStep
from app.services.zephyr_mapping import dry_run_persisted_cases, pack_traceability_description, preview_zephyr_rows


def _case(**overrides) -> TestCase:
    case = TestCase(
        release_id=1,
        test_case_id="QC-001",
        component="BRF-17442",
        test_case_name="Iniciar el flujo de contratación · WEB",
        description="desc",
        user_type=None,
        priority=TestCasePriority.CRITICAL,
        test_type=TestCaseType.FUNCTIONAL,
        status=TestCaseStatus.UNEXECUTED,
        test_data="HN: HN001\nEPCs: EPC-1\nDispositivo: WEB",
        justification="razonamiento",
        technical_story="EPC-21813, EPC-21842",
        ecosystem="OTT",
        device="WEB",
        group_id="BRF-17442:HN001:iniciar",
    )
    case.steps = [
        TestStep(step_number=1, test_step="Abrir WEB", expected_result="Sesión en WEB"),
        TestStep(step_number=2, test_step="Ejecutar HN001", expected_result="Flujo inicia"),
    ]
    for key, value in overrides.items():
        setattr(case, key, value)
    return case


def test_dry_run_does_not_invent_user_and_keeps_steps_paired() -> None:
    result = dry_run_persisted_cases([_case()])
    assert result.wrote_jira is False
    assert result.wrote_zephyr is False
    assert result.evaluated == 1
    assert result.errors == 0
    assert result.publicable == 1
    assert result.require_mapping == 1
    rows = preview_zephyr_rows(_case())
    assert len(rows) == 2
    assert rows[0]["Test Case ID"] == rows[1]["Test Case ID"] == "QC-001"
    assert rows[0]["Test Case Name"].endswith("· WEB")
    assert rows[0]["User Type"] == ""
    assert rows[0]["Step"] == "1"
    assert rows[1]["Step"] == "2"
    assert "Device: WEB" in rows[0]["Description"]
    assert rows[0]["Priority"] == "CRITICAL"
    assert rows[0]["Test Type"] == "FUNCTIONAL"
    assert rows[0]["Status"] == "UNEXECUTED"


def test_pack_traceability_skips_empty_fields() -> None:
    text = pack_traceability_description(
        description="hola",
        test_data=None,
        reasoning=None,
        brf="BRF-1",
        hn=None,
        epcs="",
        behavior="b",
        ecosystem=None,
        device=None,
        interaction_point=None,
        mdp=None,
    )
    assert "BRF: BRF-1" in text
    assert "Device:" not in text
    assert "MDP:" not in text


def test_missing_steps_is_error() -> None:
    case = _case()
    case.steps = []
    result = dry_run_persisted_cases([case])
    assert result.errors == 1
    assert result.cases[0].status == "error"
