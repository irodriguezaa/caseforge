"""Pydantic schemas for Defect."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.defect import DefectStatus
from app.models.test_case import TestCasePriority


class DefectBase(BaseModel):
    title: str = Field(min_length=1, max_length=250)
    description: str | None = None
    severity: TestCasePriority


class DefectCreate(DefectBase):
    status: DefectStatus = DefectStatus.OPEN


class DefectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=250)
    description: str | None = None
    severity: TestCasePriority | None = None
    status: DefectStatus | None = None


class DefectRead(DefectBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    test_case_id: int
    status: DefectStatus
    created_at: datetime
    updated_at: datetime
