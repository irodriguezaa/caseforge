"""QC effort from persisted Test Cases: priority minutes × complexity factor.

minutes = base(BLOCKER 20 / CRITICAL 12) × factor(BAJA 1.0 / MEDIA 1.3 / ALTA 1.6)

Calibrated to Coship 52: QC executed in ~2–2.5 days vs 4.7 with the previous 25×1.5 floor.
Complexity is classified from steps, condition and confidence only.
"""

from __future__ import annotations

from typing import Any, Literal

from app.config import settings
from app.schemas.case_generation import GeneratedCaseCandidate

Complexity = Literal["BAJA", "MEDIA", "ALTA"]

QC_HOURS_PER_DAY = 6.0
BLOCKER_MINUTES = 20
CRITICAL_MINUTES = 12
COMPLEXITY_FACTOR = {
    "BAJA": 1.0,
    "LOW": 1.0,
    "MEDIA": 1.3,
    "MEDIUM": 1.3,
    "ALTA": 1.6,
    "HIGH": 1.6,
}

# Retired count formula, kept only so reports can compare old vs new.
QC_CASES_PER_DAY_LEGACY = 46.0
QC_RELEASE_EFFORT_FACTOR_LEGACY = 3.0


def hours_per_day() -> float:
    return float(settings.qc_hours_per_day)


def classify_complexity(candidate: GeneratedCaseCandidate) -> Complexity:
    """Complejidad por forma del caso, no por prioridad.

    BAJA: validación básica de 1 paso, o 1 paso con confianza alta.
    MEDIA: condición especial, 2–3 pasos, o confianza media.
    ALTA: 4+ pasos o confianza baja.
    BLOCKER/CRITICAL no entran aquí; solo fijan la base de minutos (20 vs 12).
    """
    steps = len(candidate.steps)
    if candidate.basic_validation and steps <= 1 and not candidate.requires_condition:
        return "BAJA"
    if steps >= 4 or candidate.confidence == "low":
        return "ALTA"
    if candidate.requires_condition or steps >= 2 or candidate.confidence == "medium":
        return "MEDIA"
    return "BAJA"


def _priority_value(priority: Any) -> str:
    if priority is None:
        return "CRITICAL"
    return str(priority.value if hasattr(priority, "value") else priority).upper()


def priority_base_minutes(priority: Any) -> int:
    return BLOCKER_MINUTES if _priority_value(priority) == "BLOCKER" else CRITICAL_MINUTES


def complexity_factor(complexity: str | None) -> float:
    key = (complexity or "MEDIA").strip().upper()
    return COMPLEXITY_FACTOR.get(key, COMPLEXITY_FACTOR["MEDIA"])


def estimate_case_minutes(priority: Any, complexity: str | None) -> float:
    return round(priority_base_minutes(priority) * complexity_factor(complexity), 1)


def estimate_case_hours(priority: Any, complexity: str | None) -> float:
    return round(estimate_case_minutes(priority, complexity) / 60.0, 2)


def estimate_release_from_cases(cases: list[Any]) -> tuple[float, float]:
    """Return (hours, person-days) from real TCs. days = hours / 6."""
    if not cases:
        return 0.0, 0.0
    minutes = 0.0
    for row in cases:
        priority = getattr(row, "priority", None)
        if isinstance(row, dict):
            priority = row.get("priority")
            complexity = row.get("complexity")
        else:
            complexity = getattr(row, "complexity", None)
        minutes += estimate_case_minutes(priority, complexity)
    hours = minutes / 60.0
    days = hours / hours_per_day()
    return round(hours, 1), round(days, 1)


def duration_days(person_days: float, resources: int) -> float:
    testers = max(int(resources), 1)
    return round(person_days / testers, 1)


def estimate_release_legacy_count(test_case_count: int) -> tuple[float, float]:
    """Retired: (TC / 46) × 3 days; hours = days × 6. Comparison only."""
    count = max(int(test_case_count), 0)
    if count == 0:
        return 0.0, 0.0
    days = (count / QC_CASES_PER_DAY_LEGACY) * QC_RELEASE_EFFORT_FACTOR_LEGACY
    hours = days * QC_HOURS_PER_DAY
    return round(hours, 1), round(days, 1)
