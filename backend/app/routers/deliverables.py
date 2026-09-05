"""Deliverable endpoints.

A Deliverable groups the QC version history of one functional unit across Releases. This
router is read-focused: creation happens implicitly via get-or-create in
routers/releases.py:create_release, matching the approved "no obligatory picker" flow.
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.deliverable import Deliverable
from app.models.defect import Defect
from app.models.release import Release, ReleaseType
from app.models.test_case import TestCase
from app.routers.common import get_deliverable_or_404
from app.schemas.deliverable import DeliverableRead, DeliverableReleaseSummary, DeliverableWithMetrics

router = APIRouter(prefix="/api/v1/deliverables", tags=["deliverables"])


@router.get("", response_model=list[DeliverableRead])
def list_deliverables(
    name: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[Deliverable]:
    """`?name=` does a case-insensitive exact match -- used by the frontend to look up whether
    a typed Entregable already exists before the Release is actually created."""
    stmt = select(Deliverable).order_by(Deliverable.name)
    if name is not None:
        stmt = stmt.where(func.lower(Deliverable.name) == name.strip().lower())
    return list(db.execute(stmt).scalars().all())


@router.get("/{deliverable_id}", response_model=DeliverableWithMetrics)
def get_deliverable(deliverable_id: int, db: Session = Depends(get_db)) -> DeliverableWithMetrics:
    deliverable = get_deliverable_or_404(deliverable_id, db)

    releases = list(
        db.execute(
            select(Release)
            .where(Release.deliverable_id == deliverable_id)
            .order_by(Release.created_at.asc())
        )
        .scalars()
        .all()
    )

    total_versions = len(releases)
    total_evolutivas = sum(1 for r in releases if r.release_type == ReleaseType.EVOLUTIVO)
    total_revalidaciones = sum(1 for r in releases if r.release_type == ReleaseType.REVALIDACION)

    total_defects = 0
    if releases:
        release_ids = [r.id for r in releases]
        total_defects = db.execute(
            select(func.count(Defect.id))
            .join(TestCase, Defect.test_case_id == TestCase.id)
            .where(TestCase.release_id.in_(release_ids))
        ).scalar_one()

    latest = max(releases, key=lambda r: (r.created_at, r.id)) if releases else None

    return DeliverableWithMetrics(
        id=deliverable.id,
        name=deliverable.name,
        created_at=deliverable.created_at,
        updated_at=deliverable.updated_at,
        total_versions=total_versions,
        total_evolutivas=total_evolutivas,
        total_revalidaciones=total_revalidaciones,
        total_defects=total_defects,
        latest_release_id=latest.id if latest else None,
        latest_release_status=latest.status if latest else None,
        releases=[DeliverableReleaseSummary.model_validate(r) for r in releases],
    )


@router.get("/{deliverable_id}/releases", response_model=list[DeliverableReleaseSummary])
def list_deliverable_releases(
    deliverable_id: int, db: Session = Depends(get_db)
) -> list[Release]:
    """Backs the 'Release origen' dropdown.

    Historical versions of one Entregable: filter only by deliverable_id, never by
    Release.name. Distinct RN titles (e.g. HBO WEB vs RN-CV - WEB -16.9.0) still belong
    to the same version tree if they share the Deliverable row.
    """
    get_deliverable_or_404(deliverable_id, db)
    return list(
        db.execute(
            select(Release)
            .where(
                Release.deliverable_id == deliverable_id,
                Release.be_release_id.is_(None),
                Release.operativa_release_id.is_(None),
            )
            .order_by(Release.created_at.asc())
        )
        .scalars()
        .all()
    )
