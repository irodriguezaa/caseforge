"""Pydantic schemas for OperationalWindow and ReleaseWindow."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.window import WindowStatus


class OperationalWindowBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    start_date: date
    end_date: date
    cluster: str | None = Field(default=None, max_length=50)


class OperationalWindowCreate(OperationalWindowBase):
    status: WindowStatus = WindowStatus.PLANNED


class OperationalWindowUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    start_date: date | None = None
    end_date: date | None = None
    cluster: str | None = Field(default=None, max_length=50)
    status: WindowStatus | None = None


class OperationalWindowRead(OperationalWindowBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: WindowStatus
    created_at: datetime
    updated_at: datetime


class ReleaseWindowBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    start_date: date
    end_date: date


class ReleaseWindowCreate(ReleaseWindowBase):
    status: WindowStatus = WindowStatus.PLANNED


class ReleaseWindowUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    start_date: date | None = None
    end_date: date | None = None
    status: WindowStatus | None = None


class ReleaseWindowRead(ReleaseWindowBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    release_id: int
    status: WindowStatus
    created_at: datetime
    updated_at: datetime
