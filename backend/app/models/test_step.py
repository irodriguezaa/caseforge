"""TestStep ORM model.

Domain fields: step_number, test_step, expected_result, and optional jira_ticket
when a step fails and QC records the Jira issue.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
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
    jira_ticket: Mapped[str | None] = mapped_column(String(250), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    test_case: Mapped["TestCase"] = relationship(back_populates="steps")
