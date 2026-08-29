"""Pydantic schemas for the QC dashboard summary."""

from datetime import date

from pydantic import BaseModel, Field


class DashboardSummary(BaseModel):
    releases_total: int = 0
    releases_by_status: dict[str, int] = Field(default_factory=dict)
    test_cases_total: int = 0
    test_cases_by_status: dict[str, int] = Field(default_factory=dict)
    test_cases_by_priority: dict[str, int] = Field(default_factory=dict)


class AtRiskItem(BaseModel):
    type: str  # "operational_window" | "release_window"
    id: int
    name: str
    reasons: list[str]


class ActivityItem(BaseModel):
    """One row of 'Actividades QC en curso': an open Release and its current execution state."""

    release_id: int
    release_name: str
    release_version: str
    platform: str
    cluster: str | None
    window_name: str | None
    window_start_date: date | None = None
    window_end_date: date | None = None
    status: str  # ReleaseStatus value, e.g. "DRAFT" | "IN_PROGRESS"
    planned: int
    executed: int
    pass_count: int = 0
    fail_count: int = 0
    blocked_count: int = 0
    unexecuted_count: int = 0
    defects_blocker_count: int = 0
    percent_avance: float
    percent_cobertura: float
    risk_level: str  # "LOW" | "MEDIUM" | "HIGH"
    risk_reasons: list[str] = Field(default_factory=list)


class QcDashboardSummary(BaseModel):
    """Backs the redesigned QC Dashboard: 'what is QC doing now, how far along, what's at risk'.

    percent_avance and percent_cobertura currently share the same formula
    ((executed - i.e. non-UNEXECUTED) / planned), per explicit product decision, since there is
    no separate "expected scope" entity yet to give Cobertura a different denominator. They are
    kept as two distinct fields so Cobertura's formula can change later without touching Avance.
    """

    windows_total: int = 0
    windows_active: int = 0
    operational_windows_total: int = 0
    operational_windows_active: int = 0
    release_windows_total: int = 0
    release_windows_active: int = 0
    releases_open: int = 0
    test_cases_planned: int = 0
    test_cases_executed: int = 0
    percent_avance: float = 0.0
    percent_cobertura: float = 0.0
    pass_count: int = 0
    fail_count: int = 0
    blocked_count: int = 0
    unexecuted_count: int = 0
    defects_found: int = 0
    defects_critical: int = 0
    at_risk: list[AtRiskItem] = Field(default_factory=list)
    active_items: list[ActivityItem] = Field(default_factory=list)
