"""Pydantic schemas for QcTicket and its bulk-import pipeline (Import -> Validate -> Preview ->
Approve -> Persist, same pattern as Test Case import)."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.qc_ticket import QcTicketPriority, QcTicketSource, QcTicketView


class QcTicketBase(BaseModel):
    issue_key: str = Field(min_length=1, max_length=50)
    issue_type: str | None = None
    project_key: str | None = None
    priority_bucket: QcTicketPriority
    status_raw: str
    is_open: bool
    cluster: str | None = None
    affected_program: str | None = None
    device: str | None = None
    swf: str | None = None
    is_attributed: bool | None = None
    created_date: date
    resolved_date: date | None = None
    summary: str | None = None


class QcTicketCreate(QcTicketBase):
    view: QcTicketView
    source: QcTicketSource


class QcTicketRead(QcTicketBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    view: QcTicketView
    source: QcTicketSource
    imported_at: datetime


class QcTicketImportRowError(BaseModel):
    issue_key: str | None = None
    row_number: int | None = None
    message: str


class QcTicketImportPreviewResponse(BaseModel):
    valid: list[QcTicketCreate]
    errors: list[QcTicketImportRowError]
    warnings: list[QcTicketImportRowError] = Field(default_factory=list)
    total_rows: int
    excluded_cancelled_count: int = 0
    valid_count: int
    error_count: int


class QcTicketBulkCreateError(BaseModel):
    issue_key: str | None
    message: str


class QcTicketBulkCreateResult(BaseModel):
    created: list[QcTicketRead]
    errors: list[QcTicketBulkCreateError]


class QcTicketJiraRefreshFilterResult(BaseModel):
    filter_id: str
    source: str
    jira_count: int
    mapped: int
    skipped: int


class QcTicketJiraRefreshResult(BaseModel):
    created: int
    updated: int
    skipped: int
    filter_ids: list[str]
    filters: list[QcTicketJiraRefreshFilterResult] = Field(default_factory=list)


class QcTicketStats(BaseModel):
    """Backs the KPIs -> Radar de Defectos screen. Split by view (Operativas/Release), since
    they use different backlog-closed rules and different SWF derivations."""

    total: int
    blocker_count: int
    critical_count: int
    other_count: int
    open_count: int
    qc_detected_count: int
    leaked_count: int
    leak_rate_percent: float  # leaked / (leaked + qc_detected) * 100
    genuine_leak_count: int | None = None  # Release only: leaked AND NOT is_attributed
    by_cluster: dict[str, int] = Field(default_factory=dict)
    by_swf: dict[str, int] = Field(default_factory=dict)
    by_month: dict[str, int] = Field(default_factory=dict)  # "YYYY-MM" -> count

    # Added for the expanded dashboard (all derived from fields already stored per ticket --
    # no new ingestion, no new business rule).
    by_month_priority: dict[str, dict[str, int]] = Field(default_factory=dict)  # month -> {BLOCKER/CRITICAL/OTHER: n}
    open_by_priority: dict[str, int] = Field(default_factory=dict)  # backlog abierto, desglosado por prioridad
    by_status: dict[str, int] = Field(default_factory=dict)  # backlog abierto, desglosado por status_raw
    by_device: dict[str, int] = Field(default_factory=dict)  # por dispositivo/programa (ya agrupado CL+PR en import)
    by_program: dict[str, int] = Field(default_factory=dict)  # Operativas: por affected_program crudo
    by_quarter: dict[str, int] = Field(default_factory=dict)  # Release: "YYYY-QN" -> count
    severity_by_swf: dict[str, dict[str, int]] = Field(default_factory=dict)  # swf -> {BLOCKER/CRITICAL/OTHER: n}
    swf_by_month: dict[str, dict[str, int]] = Field(default_factory=dict)  # month -> {swf: count}
    leak_by_month: dict[str, dict[str, float]] = Field(default_factory=dict)  # month -> {"leaked": n, "rate": pct}
    leak_by_swf: dict[str, int] = Field(default_factory=dict)  # Release: fuga por SWF
    leak_by_project: dict[str, int] = Field(default_factory=dict)  # Release: fuga por project_key crudo (sin mapeo)
