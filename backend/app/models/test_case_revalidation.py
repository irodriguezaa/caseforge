"""TestCaseRevalidation ORM model (Alternative C, approved).

Records that a Revalidation Release re-tested a TestCase that already exists somewhere else in
the same Deliverable's history, WITHOUT copying or duplicating that TestCase. The original
TestCase (its definition, its steps, and its own historical `status` on its original Release)
is never touched. This row carries the revalidation's own independent execution result.

Example: V1's TE-001 stays FAIL forever. V2 (a Revalidación) adds one row here
(release_id=V2.id, test_case_id=TE-001's id, status=PASS) -- V1 is untouched, no new TestCase
was created, and V2's own result is fully independent.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.test_case import TestCaseStatus

if TYPE_CHECKING:
    from app.models.release import Release
    from app.models.test_case import TestCase


class TestCaseRevalidation(Base):
    __tablename__ = "test_case_revalidations"
    __table_args__ = (
        # A given Revalidation Release cannot list the same original TestCase twice.
        UniqueConstraint("release_id", "test_case_id", name="uq_revalidation_release_test_case"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    release_id: Mapped[int] = mapped_column(ForeignKey("releases.id", ondelete="CASCADE"), nullable=False)
    test_case_id: Mapped[int] = mapped_column(
        ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False
    )
    # Reuses the exact same TestCaseStatus enum/values TestCase itself uses -- same vocabulary,
    # independent value.
    status: Mapped[TestCaseStatus] = mapped_column(
        Enum(TestCaseStatus, name="test_case_status", native_enum=True, validate_strings=True),
        nullable=False,
        default=TestCaseStatus.UNEXECUTED,
        server_default=TestCaseStatus.UNEXECUTED.value,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    release: Mapped["Release"] = relationship()
    test_case: Mapped["TestCase"] = relationship()
