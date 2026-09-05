"""Schemas for the QC Outlook calendar module."""

from pydantic import BaseModel, Field


class QcCalendarEvent(BaseModel):
    id: str
    title: str
    start: str
    end: str
    location: str | None = None
    is_live: bool = False
    web_link: str | None = None
    categories: list[str] = Field(default_factory=list)
    source: str = "caseforge"


class QcCalendarDayResponse(BaseModel):
    date: str
    events: list[QcCalendarEvent]
    feed: str = "caseforge"
    outlook_note: str | None = None


class QcCalendarWeekResponse(BaseModel):
    week_start: str
    events: list[QcCalendarEvent]
    feed: str = "caseforge"
    outlook_note: str | None = None
