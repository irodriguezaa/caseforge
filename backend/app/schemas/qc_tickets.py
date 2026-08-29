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


class QcRadarFilterItem(BaseModel):
    filter_id: str
    label: str
    description: str
    tag: str


class QcRadarViewConfig(BaseModel):
    detected: QcRadarFilterItem
    leaked: QcRadarFilterItem


class QcRadarConfigResponse(BaseModel):
    OPERATIVAS: QcRadarViewConfig
    RELEASE: QcRadarViewConfig
