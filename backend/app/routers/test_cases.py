"""TestCase endpoints.

Includes a bulk-create endpoint (`POST /releases/{release_id}/test-cases/bulk`) whose payload
and per-row error shape are designed to be reused, unchanged, as the "Persist" stage of the
Import -> Validate -> Preview -> Approve -> Persist pipeline. The endpoint is transactional:
either every row in the batch persists, or none do -- see bulk_create_test_cases for details.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import DataError, IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models.test_case import TestCase, TestCasePriority, TestCaseStatus
from app.models.test_step import TestStep
from app.routers.common import get_release_or_404, get_test_case_or_404
from app.schemas.test_case import (
    BulkCreateError,
    TestCaseBulkCreate,
    TestCaseBulkCreateResult,
    TestCaseCreate,
    TestCaseRead,
    TestCaseReadWithSteps,
    TestCaseUpdate,
)

router = APIRouter(prefix="/api/v1", tags=["test-cases"])


def _build_test_case(release_id: int, payload: TestCaseCreate) -> TestCase:
    data = payload.model_dump(exclude={"steps"})
    test_case = TestCase(release_id=release_id, **data)
    test_case.steps = [TestStep(**step.model_dump()) for step in payload.steps]
    return test_case


@router.get("/releases/{release_id}/test-cases", response_model=list[TestCaseRead])
def list_test_cases(
    release_id: int,
    status_filter: TestCaseStatus | None = Query(default=None, alias="status"),
    priority: TestCasePriority | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[TestCase]:
    get_release_or_404(release_id, db)
    stmt = select(TestCase).where(TestCase.release_id == release_id)
    if status_filter is not None:
        stmt = stmt.where(TestCase.status == status_filter)
    if priority is not None:
        stmt = stmt.where(TestCase.priority == priority)
    stmt = stmt.order_by(TestCase.test_case_id)
    return list(db.execute(stmt).scalars().all())


@router.post(
    "/releases/{release_id}/test-cases",
    response_model=TestCaseReadWithSteps,
    status_code=status.HTTP_201_CREATED,
)
def create_test_case(
    release_id: int, payload: TestCaseCreate, db: Session = Depends(get_db)
) -> TestCase:
    get_release_or_404(release_id, db)
    test_case = _build_test_case(release_id, payload)
    db.add(test_case)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"test_case_id '{payload.test_case_id}' already exists in this release.",
        ) from exc
    db.refresh(test_case)
    return test_case


def _describe_bulk_error(exc: Exception, row: TestCaseCreate) -> str:
    if isinstance(exc, IntegrityError):
        return f"test_case_id '{row.test_case_id}' already exists in this release."
    if isinstance(exc, DataError):
        return (
            f"test_case_id '{row.test_case_id}': la base de datos rechazó uno de los valores "
            f"enviados (por ejemplo, priority='{row.priority}'). Verifica que coincida con los "
            "valores que la base de datos acepta actualmente -- puede indicar que falta aplicar "
            "una migración."
        )
    return f"test_case_id '{row.test_case_id}': error inesperado al guardar ({exc.__class__.__name__})."


@router.post(
    "/releases/{release_id}/test-cases/bulk",
    response_model=TestCaseBulkCreateResult,
    status_code=status.HTTP_201_CREATED,
)
def bulk_create_test_cases(
    release_id: int, payload: TestCaseBulkCreate, db: Session = Depends(get_db)
) -> TestCaseBulkCreateResult:
    """Persist stage for the bulk-import pipeline: create many already-approved rows.

    Transactional: every row is tried independently (via its own savepoint) so the response can
    report a precise per-row error, but nothing is persisted unless ALL rows succeed. If any row
    fails -- a duplicate test_case_id (IntegrityError), a value the database rejects such as an
    out-of-sync enum (DataError), or any other DB-level error -- the entire batch is rolled back.
    No partial import is ever left behind.
    """
    get_release_or_404(release_id, db)

    try:
        rows = []
        for row in payload.test_cases:
            test_case = _build_test_case(release_id, row)
            db.add(test_case)
            rows.append(test_case)
        db.flush()
    except SQLAlchemyError:
        db.rollback()
        tentative_created: list[TestCase] = []
        errors: list[BulkCreateError] = []

        for index, row in enumerate(payload.test_cases):
            savepoint = db.begin_nested()
            test_case = _build_test_case(release_id, row)
            db.add(test_case)
            try:
                db.flush()
            except SQLAlchemyError as exc:
                savepoint.rollback()
                errors.append(
                    BulkCreateError(
                        index=index,
                        test_case_id=row.test_case_id,
                        message=_describe_bulk_error(exc, row),
                    )
                )
                continue
            tentative_created.append(test_case)

        if errors:
            # At least one row failed: roll back the whole batch, including any rows that flushed
            # successfully above. Nothing partial is committed.
            db.rollback()
            return TestCaseBulkCreateResult(created=[], errors=errors)

        db.commit()
        for test_case in tentative_created:
            db.refresh(test_case)
        return TestCaseBulkCreateResult(created=tentative_created, errors=[])

    db.commit()
    for test_case in rows:
        db.refresh(test_case)
    return TestCaseBulkCreateResult(created=rows, errors=[])


def _assert_test_case_belongs_to_release(test_case: TestCase, release_id: int | None) -> None:
    if release_id is not None and test_case.release_id != release_id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Test case not found in this Release.",
        )


def _replace_steps(db: Session, test_case: TestCase, steps: list[dict]) -> None:
    test_case.steps.clear()
    db.flush()
    for row in steps:
        test_case.steps.append(
            TestStep(
                step_number=row["step_number"],
                test_step=row["test_step"],
                expected_result=row["expected_result"],
            )
        )


@router.get("/test-cases/{test_case_id}", response_model=TestCaseReadWithSteps)
def get_test_case(test_case_id: int, db: Session = Depends(get_db)) -> TestCase:
    stmt = (
        select(TestCase)
        .where(TestCase.id == test_case_id)
        .options(selectinload(TestCase.steps))
    )
    test_case = db.execute(stmt).scalar_one_or_none()
    if test_case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Test case not found.")
    return test_case


@router.patch("/test-cases/{test_case_id}", response_model=TestCaseReadWithSteps)
def update_test_case(
    test_case_id: int,
    payload: TestCaseUpdate,
    release_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> TestCase:
    test_case = get_test_case_or_404(test_case_id, db)
    _assert_test_case_belongs_to_release(test_case, release_id)
    updates = payload.model_dump(exclude_unset=True)
    incoming_steps = updates.pop("steps", None)
    for field, value in updates.items():
        setattr(test_case, field, value)
    if incoming_steps is not None:
        _replace_steps(db, test_case, incoming_steps)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="test_case_id already exists in this release.",
        ) from exc
    db.refresh(test_case)
    stmt = (
        select(TestCase)
        .where(TestCase.id == test_case.id)
        .options(selectinload(TestCase.steps))
    )
    return db.execute(stmt).scalar_one()


@router.delete("/test-cases/{test_case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_test_case(
    test_case_id: int,
    release_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> None:
    test_case = get_test_case_or_404(test_case_id, db)
    _assert_test_case_belongs_to_release(test_case, release_id)
    db.delete(test_case)
    db.commit()
