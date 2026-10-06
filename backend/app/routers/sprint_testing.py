"""Sprint Testing: Technical Epic progress from Jira Saved Filters."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.deps.auth import require_sprint_testing
from app.schemas.sprint_testing import SprintTestingOptions, SprintTestingRead
from app.services.jira_client import JiraApiError, JiraNotConfiguredError
from app.services.sprint_testing.service import (
    SprintTestingConfigError,
    build_sprint_testing,
    list_options,
)

router = APIRouter(
    prefix="/api/v1/sprint-testing",
    tags=["sprint-testing"],
    dependencies=[Depends(require_sprint_testing)],
)


@router.get("/options", response_model=SprintTestingOptions)
def sprint_testing_options() -> SprintTestingOptions:
    return list_options()


@router.get("", response_model=SprintTestingRead)
def sprint_testing(
    sprint: str = Query(..., description="Sprint id, e.g. 44"),
    swf: str = Query(..., description="SWF id: hitss, tata, nubiral, neoris"),
) -> SprintTestingRead:
    try:
        return build_sprint_testing(sprint, swf)
    except SprintTestingConfigError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except JiraNotConfiguredError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except JiraApiError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo consultar Jira ({exc.status_code}): {exc.detail}",
        ) from exc
