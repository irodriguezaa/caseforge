from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.release import ReleaseStatus, ReleaseType


class ReleaseAnalysisBase(BaseModel):
    pdf_filename: str
    pdf_file_path: str | None = None
    detected_name: str | None = None
    detected_version: str | None = None
    detected_platform: str | None = None
    detected_description: str | None = None
    features_count: int = 0
    qa_qc_issues_count: int = 0
    nco_issues_count: int = 0
    tri_issues_count: int = 0
    detected_devices: str | None = None
    proposed_coverage: int | None = None
    estimation_text: str | None = None
    observations: list[str] = Field(default_factory=list)
    raw_analysis: dict[str, Any] = Field(default_factory=dict)
    qc_engine_version: str = "v0.1"


class ReleaseAnalysisCreate(ReleaseAnalysisBase):
    release_id: int | None = None


class ReleaseAnalysisRead(ReleaseAnalysisBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    release_id: int | None = None
    created_at: datetime
    updated_at: datetime


class ReleaseNoteAnalyzeResponse(BaseModel):
    analysis: ReleaseAnalysisBase
    calculated_business_days: int = 0


class ReleaseBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=50)
    description: str | None = None
    platform: str = Field(min_length=1, max_length=50)
    cluster: str | None = Field(default=None, max_length=50)
    start_date: date | None = None
    end_date: date | None = None
    qc_resources: int | None = None
    execution_days: int | None = None
    validation_type: str | None = None
    jira_issue_filter: str | None = None


class ReleaseCreate(ReleaseBase):
    status: ReleaseStatus = ReleaseStatus.DRAFT
    analysis_data: ReleaseAnalysisBase | None = None
    # Entregable: free text, pre-filled from the RN analyzer's detected_name but always
    # user-editable. Backend resolves this to a Deliverable via get-or-create by name.
    deliverable_name: str | None = None
    release_type: ReleaseType | None = None
    parent_release_id: int | None = None


class ReleaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    version: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = None
    platform: str | None = Field(default=None, min_length=1, max_length=50)
    cluster: str | None = Field(default=None, max_length=50)
    status: ReleaseStatus | None = None
    start_date: date | None = None
    end_date: date | None = None
    qc_resources: int | None = None
    execution_days: int | None = None
    validation_type: str | None = None
    jira_issue_filter: str | None = None
    # DRAFT-only per product decision -- enforced in the router, not here.
    deliverable_name: str | None = None
    release_type: ReleaseType | None = None
    parent_release_id: int | None = None


class ReleaseRead(ReleaseBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: ReleaseStatus
    deliverable_id: int | None = None
    release_type: ReleaseType | None = None
    parent_release_id: int | None = None
    parent_release_name: str | None = None
    operativa_release_id: int | None = None
    be_release_id: int | None = None
    deliverable_name: str | None = None
    swf: str | None = None
    regresivo_scope: str | None = None
    affected_component: str | None = None
    created_at: datetime
    updated_at: datetime


class ReleaseWithCounts(ReleaseRead):
    test_case_count: int = 0
    latest_analysis: ReleaseAnalysisRead | None = None
    # deliverable_name is inherited from ReleaseRead (populated in the list/get routers).
