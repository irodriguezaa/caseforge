"""Schemas for the Test Case bulk-import pipeline: Import -> Validate -> Preview -> Approve -> Persist.

This module covers only the first three stages (parse the file, validate it, return a preview).
"Approve -> Persist" is handled by resubmitting the `valid` test cases from the preview response
to the existing `POST /releases/{release_id}/test-cases/bulk` endpoint (schemas/test_case.py),
which already exists and is unchanged by this feature.
"""

from pydantic import BaseModel, Field

from app.schemas.test_case import TestCaseCreate


class ImportRowError(BaseModel):
    """A validation error or non-blocking warning tied to one Test Case (by ID and/or row)."""

    test_case_id: str | None = None
    row_numbers: list[int] = Field(default_factory=list)
    message: str


class ImportPreviewResponse(BaseModel):
    valid: list[TestCaseCreate]
    errors: list[ImportRowError]
    warnings: list[ImportRowError] = Field(default_factory=list)
    format: str
    sheet_name: str
    total_rows: int
    total_test_cases: int
    valid_count: int
    error_count: int


class SheetInfo(BaseModel):
    name: str
    format: str


class ImportSheetsResponse(BaseModel):
    sheets: list[SheetInfo]
    recommended_sheet: str | None = None
