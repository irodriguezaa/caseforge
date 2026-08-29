from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.test_case import TestCasePriority, TestCaseStatus


class RevalidationCandidate(BaseModel):
    """A TestCase from elsewhere in the same Deliverable, eligible to be revalidated here."""

    test_case_id: int
    test_case_label: str  # TestCase.test_case_id, e.g. "TE-001"
    component: str
    test_case_name: str
    priority: TestCasePriority
    current_status: TestCaseStatus  # the ORIGINAL TestCase's own status -- never changed by this feature
    origin_release_id: int
    origin_release_name: str
    origin_release_version: str


class TestCaseRevalidationBulkCreate(BaseModel):
    test_case_ids: list[int] = Field(min_length=1)


class TestCaseRevalidationUpdate(BaseModel):
    status: TestCaseStatus | None = None
    notes: str | None = None


class TestCaseRevalidationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    release_id: int
    test_case_id: int
    status: TestCaseStatus
    notes: str | None
    created_at: datetime
    updated_at: datetime
    # Denormalized for display -- avoids a second round trip to fetch the original TestCase.
    test_case_label: str
    component: str
    test_case_name: str
    origin_release_id: int
    origin_release_name: str
    origin_release_version: str
