"""Homologated QC effort estimate for a Release.

The estimate is an indicator of integral QC effort, not a calendar commitment.
It is computed from persisted functional Test Cases only (count), never from
discarded Scenarios, Jira Stories, or LLM-invented hours.

Capacity mix (LOW 22 + MEDIUM 16 + HIGH 8) = 46 TC / QC day / tester.
That figure is execution capacity, not full Release effort; QC_RELEASE_EFFORT_FACTOR
covers prep, scope, conditions, evidence, incidents, revalidation, and coordination.

Calibrate later via Settings / env; do not scatter these numbers in call sites.
"""

from __future__ import annotations

from typing import Literal

from app.config import settings
from app.schemas.case_generation import GeneratedCaseCandidate

Complexity = Literal["BAJA", "MEDIA", "ALTA"]

QC_CASES_PER_DAY = 46.0
QC_RELEASE_EFFORT_FACTOR = 3.0
QC_HOURS_PER_DAY = 6.0


def cases_per_day() -> float:
    return float(settings.qc_cases_per_day)


def release_effort_factor() -> float:
    return float(settings.qc_release_effort_factor)


def hours_per_day() -> float:
    return float(settings.qc_hours_per_day)


def classify_complexity(candidate: GeneratedCaseCandidate) -> Complexity:
    """Informational bucket for Complejidad IA. Does not drive Release hours."""
    steps = len(candidate.steps)
    if candidate.basic_validation and steps <= 1 and not candidate.requires_condition:
        return "BAJA"
    if (
        candidate.priority == "BLOCKER"
        or steps >= 4
        or candidate.confidence == "low"
    ):
        return "ALTA"
    if candidate.requires_condition or steps >= 2 or candidate.confidence == "medium":
        return "MEDIA"
    return "BAJA"


def estimate_release(test_case_count: int) -> tuple[float, float]:
    """Return (hours, days) rounded for display.

    ESTIMACION_QC_DIAS = (TOTAL_TEST_CASES / 46) × 3.0
    ESTIMACION_QC_HORAS = ESTIMACION_QC_DIAS × 6
    """
    count = max(int(test_case_count), 0)
    if count == 0:
        return 0.0, 0.0
    days = (count / cases_per_day()) * release_effort_factor()
    hours = days * hours_per_day()
    return round(hours, 1), round(days, 1)


def estimate_release_raw(test_case_count: int) -> tuple[float, float]:
    """Unrounded days and hours for formula checks."""
    count = max(int(test_case_count), 0)
    if count == 0:
        return 0.0, 0.0
    days = (count / cases_per_day()) * release_effort_factor()
    hours = days * hours_per_day()
    return hours, days
