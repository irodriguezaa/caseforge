"""Bulk-import endpoints.

POST .../import/sheets   -> inspect an uploaded file's sheet(s) and their detected format,
                             without parsing rows or touching the database.
POST .../import/preview  -> parse + validate a chosen sheet/file, returning which Test Cases
                             would import cleanly and which have errors. Nothing is persisted.

Once the user approves the preview result in the UI, the frontend resubmits the `valid` list
from the preview response to the existing, unchanged `POST /releases/{release_id}/test-cases/bulk`
endpoint (see routers/test_cases.py) to actually persist it.
"""

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.test_case import TestCase
from app.routers.common import get_release_or_404
from app.schemas.imports import ImportPreviewResponse, ImportRowError, ImportSheetsResponse, SheetInfo
from app.services.imports import (
    ImportStructureError,
    list_sheets_with_recommendation,
    parse_file,
    validate_rows,
)

router = APIRouter(prefix="/api/v1", tags=["imports"])


@router.post(
    "/releases/{release_id}/test-cases/import/sheets",
    response_model=ImportSheetsResponse,
)
async def list_import_sheets(
    release_id: int, file: UploadFile, db: Session = Depends(get_db)
) -> ImportSheetsResponse:
    get_release_or_404(release_id, db)

    if file.filename is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No se recibió ningún archivo.")

    content = await file.read()
    try:
        sheets, recommended = list_sheets_with_recommendation(file.filename, content)
    except ImportStructureError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="; ".join(exc.messages)) from exc

    return ImportSheetsResponse(
        sheets=[SheetInfo(name=s["name"], format=s["format"]) for s in sheets],
        recommended_sheet=recommended,
    )


@router.post(
    "/releases/{release_id}/test-cases/import/preview",
    response_model=ImportPreviewResponse,
)
async def preview_test_case_import(
    release_id: int,
    file: UploadFile,
    sheet_name: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> ImportPreviewResponse:
    get_release_or_404(release_id, db)

    if file.filename is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No se recibió ningún archivo.")

    content = await file.read()

    try:
        fmt, rows, resolved_sheet = parse_file(file.filename, content, sheet_name=sheet_name)
    except ImportStructureError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="; ".join(exc.messages)) from exc

    valid, errors, warnings = validate_rows(rows, fmt)

    # Duplicate-against-existing-data check: needs the DB, so it happens here, not in the
    # pure parser. Any test_case_id already present in this release is moved from valid to
    # errors, so the preview reflects exactly what the Persist step would accept.
    existing_ids = set(
        db.execute(
            select(TestCase.test_case_id).where(TestCase.release_id == release_id)
        ).scalars()
    )
    still_valid = []
    for test_case in valid:
        if test_case.test_case_id in existing_ids:
            errors.append(
                ImportRowError(
                    test_case_id=test_case.test_case_id,
                    row_numbers=[],
                    message=f"Test Case '{test_case.test_case_id}' ya existe en esta release.",
                )
            )
        else:
            still_valid.append(test_case)

    return ImportPreviewResponse(
        valid=still_valid,
        errors=errors,
        warnings=warnings,
        format=fmt,
        sheet_name=resolved_sheet,
        total_rows=len(rows),
        total_test_cases=len(still_valid) + len(errors),
        valid_count=len(still_valid),
        error_count=len(errors),
    )
