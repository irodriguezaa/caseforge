"""Release CRUD endpoints.

Deletion rule (per product decision): a Release can only be hard-deleted while it is still
DRAFT (cascading to its test cases/steps is safe at that point because nothing else can
reference them yet). Any release that has moved past DRAFT is considered to have activity and
must be moved to CANCELLED via PATCH instead of being deleted. This cascade behavior should be
re-reviewed before Sprint 3 once executions/evidence exist.
"""

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.release import Release, ReleaseStatus
from app.models.release_analysis import ReleaseAnalysis
from app.models.test_case import TestCase
from app.routers.common import get_release_or_404
from app.schemas.release import (
    ReleaseAnalysisRead,
    ReleaseCreate,
    ReleaseNoteAnalyzeResponse,
    ReleaseRead,
    ReleaseUpdate,
    ReleaseWithCounts,
)
from app.services.release_note_analyzer import (
    RuleBasedPdfAnalyzer,
    calculate_business_days,
)

router = APIRouter(prefix="/api/v1/releases", tags=["releases"])

# Allowed forward transitions. DRAFT can also be removed entirely via DELETE (see below).
_VALID_TRANSITIONS: dict[ReleaseStatus, set[ReleaseStatus]] = {
    ReleaseStatus.DRAFT: {ReleaseStatus.IN_PROGRESS, ReleaseStatus.CANCELLED},
    ReleaseStatus.IN_PROGRESS: {ReleaseStatus.COMPLETED, ReleaseStatus.CANCELLED},
    ReleaseStatus.COMPLETED: set(),
    ReleaseStatus.CANCELLED: set(),
}


@router.post("/analyze-rn", response_model=ReleaseNoteAnalyzeResponse)
async def analyze_release_note(
    file: UploadFile = File(...),
) -> ReleaseNoteAnalyzeResponse:
    """Parses a Release Note PDF deterministically, extracting metadata and section counts.

    Does not hallucinate or predict test cases (strictly adheres to Phase 1 separation of
    concerns prior to .md QC engine integration).
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Solo se aceptan archivos PDF para el análisis de Release Note.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="El archivo PDF está vacío.")

    analyzer = RuleBasedPdfAnalyzer()
    extracted = analyzer.analyze(file.filename, content)

    return ReleaseNoteAnalyzeResponse(
        analysis=extracted,
        calculated_business_days=0,
    )


@router.get("", response_model=list[ReleaseWithCounts])
def list_releases(
    status_filter: ReleaseStatus | None = Query(default=None, alias="status"),
    platform: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[ReleaseWithCounts]:
    stmt = (
        select(Release, func.count(TestCase.id))
        .outerjoin(TestCase, TestCase.release_id == Release.id)
        .group_by(Release.id)
        .order_by(Release.created_at.desc())
    )
    if status_filter is not None:
        stmt = stmt.where(Release.status == status_filter)
    if platform is not None:
        stmt = stmt.where(Release.platform == platform)

    rows = db.execute(stmt).all()
    results: list[ReleaseWithCounts] = []
    for release, count in rows:
        latest_analysis = (
            db.execute(
                select(ReleaseAnalysis)
                .where(ReleaseAnalysis.release_id == release.id)
                .order_by(ReleaseAnalysis.created_at.desc())
            )
            .scalars()
            .first()
        )
        release_read = ReleaseRead.model_validate(release).model_dump()
        results.append(
            ReleaseWithCounts(
                **release_read,
                test_case_count=count,
                latest_analysis=(
                    ReleaseAnalysisRead.model_validate(latest_analysis)
                    if latest_analysis
                    else None
                ),
            )
        )
    return results


@router.post("", response_model=ReleaseRead, status_code=status.HTTP_201_CREATED)
def create_release(payload: ReleaseCreate, db: Session = Depends(get_db)) -> Release:
    release_dict = payload.model_dump(exclude={"analysis_data"})
    if release_dict.get("execution_days") is None and release_dict.get("start_date") and release_dict.get("end_date"):
        release_dict["execution_days"] = calculate_business_days(
            release_dict["start_date"], release_dict["end_date"]
        )

    release = Release(**release_dict)
    db.add(release)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="A release with this name, version and platform already exists.",
        ) from exc

    if payload.analysis_data is not None:
        analysis_dict = payload.analysis_data.model_dump()
        analysis_row = ReleaseAnalysis(release_id=release.id, **analysis_dict)
        db.add(analysis_row)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="A release with this name, version and platform already exists.",
        ) from exc

    db.refresh(release)
    return release


@router.get("/{release_id}", response_model=ReleaseRead)
def get_release(release_id: int, db: Session = Depends(get_db)) -> Release:
    return get_release_or_404(release_id, db)


@router.patch("/{release_id}", response_model=ReleaseRead)
def update_release(
    release_id: int, payload: ReleaseUpdate, db: Session = Depends(get_db)
) -> Release:
    release = get_release_or_404(release_id, db)
    updates = payload.model_dump(exclude_unset=True)

    new_status = updates.get("status")
    if new_status is not None and new_status != release.status:
        allowed = _VALID_TRANSITIONS.get(release.status, set())
        if new_status not in allowed:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=(
                    f"Cannot transition release from {release.status.value} "
                    f"to {new_status.value}."
                ),
            )

    for field, value in updates.items():
        setattr(release, field, value)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="A release with this name, version and platform already exists.",
        ) from exc
    db.refresh(release)
    return release


@router.delete("/{release_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_release(release_id: int, db: Session = Depends(get_db)) -> None:
    release = get_release_or_404(release_id, db)
    if release.status != ReleaseStatus.DRAFT:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                "Only DRAFT releases can be deleted. Releases with activity must be moved to "
                "CANCELLED instead of being deleted."
            ),
        )
    db.delete(release)
    db.commit()


@router.get("/{release_id}/analysis", response_model=ReleaseAnalysisRead)
def get_release_analysis(release_id: int, db: Session = Depends(get_db)) -> ReleaseAnalysis:
    get_release_or_404(release_id, db)
    analysis = (
        db.execute(
            select(ReleaseAnalysis)
            .where(ReleaseAnalysis.release_id == release_id)
            .order_by(ReleaseAnalysis.created_at.desc())
        )
        .scalars()
        .first()
    )
    if not analysis:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="No se encontró ningún análisis de Release Note para esta release.",
        )
    return analysis


@router.post("/{release_id}/generate-cases")
def generate_cases_from_rn(release_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Stub endpoint prepared for the future .md-based QC Engine."""
    release = get_release_or_404(release_id, db)
    analysis = (
        db.execute(
            select(ReleaseAnalysis)
            .where(ReleaseAnalysis.release_id == release_id)
            .order_by(ReleaseAnalysis.created_at.desc())
        )
        .scalars()
        .first()
    )
    return {
        "status": "READY",
        "message": "Flujo de generación preparado. El motor QC v0.1 se conectará en la siguiente fase.",
        "release_id": release.id,
        "release_name": release.name,
        "validation_type": release.validation_type or "Smoke",
        "has_analysis": analysis is not None,
    }
