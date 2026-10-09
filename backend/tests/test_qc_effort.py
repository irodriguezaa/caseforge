import logging

from app.services.qc_effort import (
    estimate_case_minutes,
    estimate_release_from_cases,
    duration_days,
)
from app.services.test_case_export import _case_hours


def test_six_priority_complexity_combinations() -> None:
    assert estimate_case_minutes("CRITICAL", "BAJA") == 10
    assert estimate_case_minutes("CRITICAL", "MEDIA") == 15
    assert estimate_case_minutes("CRITICAL", "ALTA") == 20
    assert estimate_case_minutes("BLOCKER", "BAJA") == 15
    assert estimate_case_minutes("BLOCKER", "MEDIA") == 25
    assert estimate_case_minutes("BLOCKER", "ALTA") == 35


def test_defaults_when_priority_or_complexity_missing() -> None:
    assert estimate_case_minutes(None, "BAJA") == 10
    assert estimate_case_minutes("", "ALTA") == 20
    assert estimate_case_minutes("CRITICAL", None) == 15
    assert estimate_case_minutes("BLOCKER", "") == 25
    assert estimate_case_minutes(None, None) == 15


def test_normalizes_case_and_aliases() -> None:
    assert estimate_case_minutes("blocker", "baja") == 15
    assert estimate_case_minutes(" Critical ", " media ") == 15
    assert estimate_case_minutes("CRITICAL", "LOW") == 10
    assert estimate_case_minutes("BLOCKER", "HIGH") == 35
    assert estimate_case_minutes("critical", "medium") == 15


def test_unknown_values_log_and_use_documented_defaults(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="app.services.qc_effort"):
        assert estimate_case_minutes("URGENT", "BAJA") == 10
        assert estimate_case_minutes("CRITICAL", "EXTREMA") == 15
    text = caplog.text
    assert "prioridad desconocida" in text
    assert "complejidad desconocida" in text
    assert "URGENT" in text
    assert "EXTREMA" in text


def test_minutes_hours_and_person_days_from_mixed_release() -> None:
    cases = (
        [{"priority": "CRITICAL", "complexity": "BAJA"}] * 2
        + [{"priority": "CRITICAL", "complexity": "MEDIA"}] * 3
        + [{"priority": "BLOCKER", "complexity": "ALTA"}]
    )
    minutes = sum(estimate_case_minutes(row["priority"], row["complexity"]) for row in cases)
    assert minutes == 100
    hours, days = estimate_release_from_cases(cases)
    assert hours == 1.6667
    assert days == 0.2778


def test_effort_recalculates_for_filtered_subset() -> None:
    cases = (
        [{"priority": "CRITICAL", "complexity": "BAJA"}] * 2
        + [{"priority": "CRITICAL", "complexity": "MEDIA"}] * 3
        + [{"priority": "BLOCKER", "complexity": "ALTA"}]
    )
    full_hours, full_days = estimate_release_from_cases(cases)
    filtered = [row for row in cases if row["complexity"] == "BAJA"]
    hours, days = estimate_release_from_cases(filtered)
    assert len(filtered) == 2
    assert hours == round(20 / 60, 4)
    assert days == round((20 / 60) / 6, 4)
    assert hours < full_hours
    assert days < full_days


def test_effort_independent_of_calendar_window() -> None:
    cases = [{"priority": "CRITICAL", "complexity": "MEDIA"}] * 3
    hours, person_days = estimate_release_from_cases(cases)
    assert hours == 0.75
    assert person_days == 0.125
    assert duration_days(2.4, 2) == 1.2
    assert duration_days(2.4, 1) == 2.4


def test_export_avance_hours_use_same_matrix() -> None:
    from types import SimpleNamespace

    case = SimpleNamespace(priority="BLOCKER", complexity="ALTA", estimation_hours=9.9)
    assert _case_hours(case) == round(35 / 60, 2)
