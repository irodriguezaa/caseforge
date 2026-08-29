"""TestCaseRevalidation endpoints (Alternative C).

Never creates or duplicates a TestCase. A revalidation candidate is always an existing
TestCase from ANOTHER Release under the same Deliverable (not necessarily the immediate
parent_release_id -- a later Revalidación can re-touch a case that first appeared in V1).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.release import Release, ReleaseType
from app.models.test_case import TestCase
from app.models.test_case_revalidation import TestCaseRevalidation
from app.routers.common import get_release_or_404
from app.schemas.test_case_revalidation import (
    RevalidationCandidate,
    TestCaseRevalidationBulkCreate,
    TestCaseRevalidationRead,
    TestCaseRevalidationUpdate,
)

router = APIRouter(tags=["test-case-revalidations"])


def _read_with_test_case_info(revalidation: TestCaseRevalidation) -> TestCaseRevalidationRead:
    tc = revalidation.test_case
    return TestCaseRevalidationRead(
        id=revalidation.id,
        release_id=revalidation.release_id,
        test_case_id=revalidation.test_case_id,
        status=revalidation.status,
        notes=revalidation.notes,
        created_at=revalidation.created_at,
        updated_at=revalidation.updated_at,
        test_case_label=tc.test_case_id,
        component=tc.component,
        test_case_name=tc.test_case_name,
        origin_release_id=tc.release.id,
        origin_release_name=tc.release.name,
        origin_release_version=tc.release.version,
    )


@router.get(
    "/api/v1/releases/{release_id}/revalidation-candidates",
    response_model=list[RevalidationCandidate],
)
def list_revalidation_candidates(release_id: int, db: Session = Depends(get_db)) -> list[RevalidationCandidate]:
    release = get_release_or_404(release_id, db)
    if release.deliverable_id is None:
        return []  # No Deliverable yet -> no cross-release history to draw candidates from.

    already_added = set(
        db.execute(
            select(TestCaseRevalidation.test_case_id).where(TestCaseRevalidation.release_id == release_id)
        ).scalars()
    )

    stmt = (
        select(TestCase)
        .join(Release, TestCase.release_id == Release.id)
        .where(Release.deliverable_id == release.deliverable_id, TestCase.release_id != release_id)
        .order_by(Release.created_at.asc(), TestCase.test_case_id.asc())
    )
    candidates = []
    for tc in db.execute(stmt).scalars().all():
        if tc.id in already_added:
            continue
        candidates.append(
            RevalidationCandidate(
                test_case_id=tc.id,
                test_case_label=tc.test_case_id,
                component=tc.component,
                test_case_name=tc.test_case_name,
                priority=tc.priority,
                current_status=tc.status,
                origin_release_id=tc.release.id,
                origin_release_name=tc.release.name,
                origin_release_version=tc.release.version,
            )
        )
    return candidates


@router.post(
    "/api/v1/releases/{release_id}/revalidations",
    response_model=list[TestCaseRevalidationRead],
    status_code=status.HTTP_201_CREATED,
)
def create_revalidations(
    release_id: int, payload: TestCaseRevalidationBulkCreate, db: Session = Depends(get_db)
) -> list[TestCaseRevalidationRead]:
    release = get_release_or_404(release_id, db)
    if release.release_type != ReleaseType.REVALIDACION:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Solo una Release de tipo Revalidación puede registrar revalidaciones de Test Cases.",
        )

    if len(set(payload.test_case_ids)) != len(payload.test_case_ids):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No se puede seleccionar el mismo Test Case más de una vez en la misma Revalidación.",
        )

    rows: list[TestCaseRevalidation] = []
    for test_case_id in payload.test_case_ids:
        test_case = db.get(TestCase, test_case_id)
        if test_case is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Test Case {test_case_id} no encontrado.")
        if test_case.release.deliverable_id != release.deliverable_id or release.deliverable_id is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"Test Case {test_case.test_case_id} no pertenece al mismo Entregable.",
            )
        rows.append(TestCaseRevalidation(release_id=release_id, test_case_id=test_case_id))

    db.add_all(rows)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Uno o más Test Cases ya estaban agregados a esta Revalidación.",
        ) from exc

    for row in rows:
        db.refresh(row)
    return [_read_with_test_case_info(row) for row in rows]


@router.get(
    "/api/v1/releases/{release_id}/revalidations",
    response_model=list[TestCaseRevalidationRead],
)
def list_revalidations(release_id: int, db: Session = Depends(get_db)) -> list[TestCaseRevalidationRead]:
    get_release_or_404(release_id, db)
    rows = list(
        db.execute(
            select(TestCaseRevalidation)
            .where(TestCaseRevalidation.release_id == release_id)
            .order_by(TestCaseRevalidation.created_at.asc())
        )
        .scalars()
        .all()
    )
    return [_read_with_test_case_info(row) for row in rows]


@router.patch("/api/v1/revalidations/{revalidation_id}", response_model=TestCaseRevalidationRead)
def update_revalidation(
    revalidation_id: int, payload: TestCaseRevalidationUpdate, db: Session = Depends(get_db)
) -> TestCaseRevalidationRead:
    revalidation = db.get(TestCaseRevalidation, revalidation_id)
    if revalidation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Revalidation not found.")

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(revalidation, field, value)

    db.commit()
    db.refresh(revalidation)
    return _read_with_test_case_info(revalidation)
