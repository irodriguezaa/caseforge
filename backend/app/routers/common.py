"""Shared lookup helpers used by the Sprint 2 domain routers."""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.release import Release
from app.models.test_case import TestCase
from app.models.test_step import TestStep


def get_release_or_404(release_id: int, db: Session) -> Release:
    release = db.get(Release, release_id)
    if release is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Release not found.")
    return release


def get_test_case_or_404(test_case_id: int, db: Session) -> TestCase:
    test_case = db.get(TestCase, test_case_id)
    if test_case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Test case not found.")
    return test_case


def get_test_step_or_404(step_id: int, db: Session) -> TestStep:
    step = db.get(TestStep, step_id)
    if step is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Test step not found.")
    return step
