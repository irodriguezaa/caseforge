"""Pydantic schemas for TestCase.

TestCaseBulkCreate/TestCaseBulkCreateResult exist so that a future Excel/CSV import pipeline
(Import -> Validate -> Preview -> Approve -> Persist) can reuse this exact "Persist" contract:
once rows are validated and approved elsewhere, they are submitted here in the same shape a
human-driven bulk creation would use. No import parsing/staging is implemented in Sprint 2.
"""

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.test_case import TestCasePriority, TestCaseStatus, TestCaseType
from app.schemas.test_step import TestStepCreate, TestStepRead

_TEST_CASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


class TestCaseBase(BaseModel):
    test_case_id: str = Field(min_length=1, max_length=20)
    component: str = Field(min_length=1, max_length=150)
    test_case_name: str = Field(min_length=1, max_length=250)
    description: str | None = None
    user_type: str | None = Field(default=None, max_length=100)
    priority: TestCasePriority = TestCasePriority.CRITICAL
    test_type: TestCaseType = TestCaseType.FUNCTIONAL
    test_data: str | None = None
    requires_condition: bool = False
    evidence: str | None = None
    justification: str | None = None
    technical_epic: str | None = Field(default=None, max_length=250)
    technical_story: str | None = Field(default=None, max_length=500)
    scenario_origin: str | None = None
    related_rn: str | None = Field(default=None, max_length=250)
    confidence: str | None = Field(default=None, max_length=16)
    complexity: str | None = Field(default=None, max_length=16)
    estimation_hours: float | None = None
    generated_by_engine: bool = False
    ecosystem: str | None = Field(default=None, max_length=16)
    device: str | None = Field(default=None, max_length=80)
    device_source: str | None = Field(default=None, max_length=250)
    applicability_reason: str | None = None
    duplicate_status: str | None = Field(default=None, max_length=32)
    group_id: str | None = Field(default=None, max_length=80)
    hn_source: str | None = Field(default=None, max_length=32)

    @field_validator("estimation_hours", mode="before")
    @classmethod
    def _coerce_hours(cls, value: object) -> float | None:
        if value is None or value == "":
            return None
        return float(value)

    @field_validator("test_case_id")
    @classmethod
    def _validate_test_case_id_format(cls, value: str) -> str:
        if not _TEST_CASE_ID_PATTERN.match(value):
            raise ValueError(
                "test_case_id must be alphanumeric and may include '-' or '_' (e.g. 'QC-001')."
            )
        return value


class TestCaseCreate(TestCaseBase):
    status: TestCaseStatus = TestCaseStatus.UNEXECUTED
    steps: list[TestStepCreate] = Field(default_factory=list)
    operational_window_id: int | None = None
    release_window_id: int | None = None

    @model_validator(mode="after")
    def _validate_unique_step_numbers(self) -> "TestCaseCreate":
        numbers = [step.step_number for step in self.steps]
        if len(numbers) != len(set(numbers)):
            raise ValueError("step_number values must be unique within a test case.")
        return self


class TestCaseUpdate(BaseModel):
    test_case_id: str | None = Field(default=None, min_length=1, max_length=20)
    component: str | None = Field(default=None, min_length=1, max_length=150)
    test_case_name: str | None = Field(default=None, min_length=1, max_length=250)
    description: str | None = None
    user_type: str | None = Field(default=None, max_length=100)
    priority: TestCasePriority | None = None
    test_type: TestCaseType | None = None
    status: TestCaseStatus | None = None
    operational_window_id: int | None = None
    release_window_id: int | None = None
    steps: list[TestStepCreate] | None = None

    @field_validator("test_case_id")
    @classmethod
    def _validate_test_case_id_format(cls, value: str | None) -> str | None:
        if value is not None and not _TEST_CASE_ID_PATTERN.match(value):
            raise ValueError(
                "test_case_id must be alphanumeric and may include '-' or '_' (e.g. 'QC-001')."
            )
        return value

    @model_validator(mode="after")
    def _validate_unique_step_numbers(self) -> "TestCaseUpdate":
        if self.steps is None:
            return self
        numbers = [step.step_number for step in self.steps]
        if len(numbers) != len(set(numbers)):
            raise ValueError("step_number values must be unique within a test case.")
        return self


class TestCaseRead(TestCaseBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    release_id: int
    status: TestCaseStatus
    operational_window_id: int | None = None
    release_window_id: int | None = None
    created_at: datetime
    updated_at: datetime


class TestCaseReadWithSteps(TestCaseRead):
    steps: list[TestStepRead] = Field(default_factory=list)


class TestCaseBulkCreate(BaseModel):
    test_cases: list[TestCaseCreate] = Field(min_length=1)


class BulkCreateError(BaseModel):
    index: int
    test_case_id: str | None = None
    message: str


class TestCaseBulkCreateResult(BaseModel):
    created: list[TestCaseReadWithSteps]
    errors: list[BulkCreateError]
