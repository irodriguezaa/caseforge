"""Defect endpoints. A Defect always belongs to exactly one TestCase."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.defect import Defect
from app.routers.common import get_test_case_or_404
from app.schemas.defect import DefectCreate, DefectRead, DefectUpdate

router = APIRouter(prefix="/api/v1", tags=["defects"])


def _get_or_404(defect_id: int, db: Session) -> Defect:
    defect = db.get(Defect, defect_id)
    if defect is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Defect not found.")
    return defect


@router.get("/test-cases/{test_case_id}/defects", response_model=list[DefectRead])
def list_defects(test_case_id: int, db: Session = Depends(get_db)) -> list[Defect]:
    get_test_case_or_404(test_case_id, db)
    stmt = select(Defect).where(Defect.test_case_id == test_case_id).order_by(Defect.created_at.desc())
    return list(db.execute(stmt).scalars().all())


@router.post(
    "/test-cases/{test_case_id}/defects", response_model=DefectRead, status_code=status.HTTP_201_CREATED
)
def create_defect(test_case_id: int, payload: DefectCreate, db: Session = Depends(get_db)) -> Defect:
    get_test_case_or_404(test_case_id, db)
    defect = Defect(test_case_id=test_case_id, **payload.model_dump())
    db.add(defect)
    db.commit()
    db.refresh(defect)
    return defect


@router.patch("/defects/{defect_id}", response_model=DefectRead)
def update_defect(defect_id: int, payload: DefectUpdate, db: Session = Depends(get_db)) -> Defect:
    defect = _get_or_404(defect_id, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(defect, field, value)
    db.commit()
    db.refresh(defect)
    return defect


@router.delete("/defects/{defect_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_defect(defect_id: int, db: Session = Depends(get_db)) -> None:
    defect = _get_or_404(defect_id, db)
    db.delete(defect)
    db.commit()
