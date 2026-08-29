"""Pydantic schemas for TestStep."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TestStepBase(BaseModel):
    step_number: int = Field(ge=1)
    test_step: str = Field(min_length=1)
    expected_result: str = Field(min_length=1)


class TestStepCreate(TestStepBase):
    pass


class TestStepUpdate(BaseModel):
    step_number: int | None = Field(default=None, ge=1)
    test_step: str | None = Field(default=None, min_length=1)
    expected_result: str | None = Field(default=None, min_length=1)


class TestStepRead(TestStepBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    test_case_id: int
    created_at: datetime
    updated_at: datetime


class StepReorderItem(BaseModel):
    id: int
    step_number: int = Field(ge=1)


class StepReorderRequest(BaseModel):
    steps: list[StepReorderItem] = Field(min_length=1)
