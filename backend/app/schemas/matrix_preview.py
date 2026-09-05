"""Preview-only expansion of coverage matrix rows into device-level Test Cases."""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.coverage_matrix import CoverageMatrixRow


class PreviewTestCase(BaseModel):
    """One preview TC. Matrix fields are copied; execution context (device, country) is expanded."""

    brf_key: str
    hn_keys: list[str] = Field(default_factory=list)
    behavior_key: str
    behavior_title: str
    interaction_points: list[str] = Field(default_factory=list)
    channel: str | None = None
    ecosystem: str | None = None
    device: str | None = None
    country: str | None = None
    use_case_key: str = "default"
    use_case_title: str | None = None
    user_type: str | None = None
    access_path: str | None = None
    polarity: Literal["positive", "negative"] | None = None
    applicable_devices: list[str] = Field(default_factory=list)
    relevant_users: list[str] = Field(default_factory=list)
    transactional: bool = False
    mdp: list[str] = Field(default_factory=list)
    test_data: str | None = None
    epc_keys: list[str] = Field(default_factory=list)
    origin: Literal["directo", "derivado", "inferencia", "QC_REVIEW"] = "directo"
    scope_status: Literal["IN_SCOPE", "OUT_OF_SCOPE"] = "IN_SCOPE"
    duplicate_risk: Literal["UNIQUE", "POSSIBLE_DUPLICATE", "OVERLAP"] = "UNIQUE"
    duplicate_with: list[str] = Field(default_factory=list)
    reasoning: str | None = None
    evidence: str
    expansion_reason: str


class PreviewReportRow(BaseModel):
    brf_key: str
    hn: str
    behavior: str
    device: str
    channel: str
    generated: bool
    reason: str


class PreviewBrfSummary(BaseModel):
    brf_key: str
    matrix_rows: int = 0
    executable_rows: int = 0
    devices_expanded: int = 0
    preview_tcs: int = 0
    qc_review_omitted: int = 0
    out_of_scope_omitted: int = 0
    warnings: int = 0


class MatrixPreviewResponse(BaseModel):
    status: Literal["PREVIEW"] = "PREVIEW"
    engine: str
    release_id: int
    release_name: str
    persisted: bool = False
    jira: bool = False
    zephyr: bool = False
    matrix_row_count: int = 0
    preview_tc_count: int = 0
    cases: list[PreviewTestCase] = Field(default_factory=list)
    report: list[PreviewReportRow] = Field(default_factory=list)
    summary: list[PreviewBrfSummary] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_matrix: list[CoverageMatrixRow] = Field(default_factory=list)
