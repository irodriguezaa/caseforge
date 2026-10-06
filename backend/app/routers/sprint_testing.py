"""Sprint Testing: Technical Epic progress from Jira Saved Filters."""

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.deps.auth import require_sprint_testing
from app.schemas.sprint_testing import SprintTestingOptions, SprintTestingRead
from app.services.jira_client import JiraApiError, JiraNotConfiguredError
from app.services.sprint_testing.service import (
    SprintTestingConfigError,
    build_execution_issues_xlsx,
    build_executive_report_pptx,
    build_sprint_testing,
    list_options,
)

router = APIRouter(
    prefix="/api/v1/sprint-testing",
    tags=["sprint-testing"],
    dependencies=[Depends(require_sprint_testing)],
)


def _raise_sprint_testing(exc: Exception) -> None:
    if isinstance(exc, SprintTestingConfigError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if isinstance(exc, JiraNotConfiguredError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if isinstance(exc, JiraApiError):
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo consultar Jira ({exc.status_code}): {exc.detail}",
        ) from exc
    raise exc


def _attachment(payload: bytes, filename: str, media_type: str) -> Response:
    ascii_name = filename.encode("ascii", "ignore").decode("ascii") or "export"
    disposition = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
    return Response(
        content=payload,
        media_type=media_type,
        headers={
            "Content-Disposition": disposition,
            "Content-Length": str(len(payload)),
        },
    )


@router.get("/options", response_model=SprintTestingOptions)
def sprint_testing_options() -> SprintTestingOptions:
    return list_options()


@router.get("/export/issues")
def sprint_testing_export_issues(
    sprint: str = Query(..., description="Sprint id, e.g. 44"),
    swf: str = Query(..., description="SWF id: hitss, tata, nubiral, neoris"),
) -> Response:
    try:
        payload, filename = build_execution_issues_xlsx(sprint, swf)
    except (SprintTestingConfigError, JiraNotConfiguredError, JiraApiError) as exc:
        _raise_sprint_testing(exc)
        raise
    return _attachment(
        payload,
        filename,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/export/report")
def sprint_testing_export_report(
    sprint: str = Query(..., description="Sprint id, e.g. 44"),
    swf: str = Query(..., description="SWF id: hitss, tata, nubiral, neoris"),
) -> Response:
    try:
        payload, filename = build_executive_report_pptx(sprint, swf)
    except (SprintTestingConfigError, JiraNotConfiguredError, JiraApiError) as exc:
        _raise_sprint_testing(exc)
        raise
    return _attachment(
        payload,
        filename,
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )


@router.get("", response_model=SprintTestingRead)
def sprint_testing(
    sprint: str = Query(..., description="Sprint id, e.g. 44"),
    swf: str = Query(..., description="SWF id: hitss, tata, nubiral, neoris"),
) -> SprintTestingRead:
    try:
        return build_sprint_testing(sprint, swf)
    except (SprintTestingConfigError, JiraNotConfiguredError, JiraApiError) as exc:
        _raise_sprint_testing(exc)
        raise
