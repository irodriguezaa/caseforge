"""QC-XXX labels increment by 1 from the highest existing number in the release."""

from app.services.case_persistence import next_test_case_id


def test_first_case_is_qc_001() -> None:
    assert next_test_case_id([]) == "QC-001"


def test_increments_by_one_from_highest_qc_label() -> None:
    assert next_test_case_id(["QC-001", "QC-003", "QC-009"]) == "QC-010"


def test_ignores_non_qc_labels() -> None:
    assert next_test_case_id(["MAN-001", "QC-002"]) == "QC-003"
