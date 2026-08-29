"""TestStep ORM model.

A TestStep carries only three domain fields, as specified: step_number, test_step, and
expected_result. It intentionally does not duplicate any TestCase concept (no name,
description, priority, etc. at the step level).
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.test_case import TestCase


class TestStep(Base):
    """A single ordered step within a TestCase."""

    __tablename__ = "test_steps"
    __table_args__ = (
        UniqueConstraint("test_case_id", "step_number", name="uq_test_step_case_step_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    test_case_id: Mapped[int] = mapped_column(
        ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False
    )
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    test_step: Mapped[str] = mapped_column(Text, nullable=False)
    expected_result: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    test_case: Mapped["TestCase"] = relationship(back_populates="steps")
