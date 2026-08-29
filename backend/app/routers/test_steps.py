"""TestStep endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.test_step import TestStep
from app.routers.common import get_test_case_or_404, get_test_step_or_404
from app.schemas.test_step import (
    StepReorderRequest,
    TestStepCreate,
    TestStepRead,
    TestStepUpdate,
)

router = APIRouter(prefix="/api/v1", tags=["test-steps"])


@router.get("/test-cases/{test_case_id}/steps", response_model=list[TestStepRead])
def list_steps(test_case_id: int, db: Session = Depends(get_db)) -> list[TestStep]:
    get_test_case_or_404(test_case_id, db)
    stmt = (
        select(TestStep)
        .where(TestStep.test_case_id == test_case_id)
        .order_by(TestStep.step_number)
    )
    return list(db.execute(stmt).scalars().all())


@router.post(
    "/test-cases/{test_case_id}/steps",
    response_model=TestStepRead,
    status_code=status.HTTP_201_CREATED,
)
def create_step(
    test_case_id: int, payload: TestStepCreate, db: Session = Depends(get_db)
) -> TestStep:
    get_test_case_or_404(test_case_id, db)
    step = TestStep(test_case_id=test_case_id, **payload.model_dump())
    db.add(step)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"step_number {payload.step_number} already exists for this test case.",
        ) from exc
    db.refresh(step)
    return step


@router.patch("/steps/{step_id}", response_model=TestStepRead)
def update_step(step_id: int, payload: TestStepUpdate, db: Session = Depends(get_db)) -> TestStep:
    step = get_test_step_or_404(step_id, db)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(step, field, value)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="step_number already exists for this test case.",
        ) from exc
    db.refresh(step)
    return step


@router.delete("/steps/{step_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_step(step_id: int, db: Session = Depends(get_db)) -> None:
    step = get_test_step_or_404(step_id, db)
    db.delete(step)
    db.commit()


@router.put("/test-cases/{test_case_id}/steps/reorder", response_model=list[TestStepRead])
def reorder_steps(
    test_case_id: int, payload: StepReorderRequest, db: Session = Depends(get_db)
) -> list[TestStep]:
    get_test_case_or_404(test_case_id, db)

    steps = {
        step.id: step
        for step in db.execute(
            select(TestStep).where(TestStep.test_case_id == test_case_id)
        ).scalars()
    }

    requested_ids = {item.id for item in payload.steps}
    if not requested_ids.issubset(steps.keys()):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="One or more step ids do not belong to this test case.",
        )

    new_numbers = [item.step_number for item in payload.steps]
    if len(new_numbers) != len(set(new_numbers)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="step_number values must be unique.")

    # Two-phase update avoids violating the (test_case_id, step_number) unique constraint
    # while numbers are being swapped: first move everything to negative placeholders, then
    # apply the final requested numbers.
    for offset, item in enumerate(payload.steps, start=1):
        steps[item.id].step_number = -offset
    db.flush()
    for item in payload.steps:
        steps[item.id].step_number = item.step_number
    db.commit()

    stmt = (
        select(TestStep)
        .where(TestStep.test_case_id == test_case_id)
        .order_by(TestStep.step_number)
    )
    return list(db.execute(stmt).scalars().all())
