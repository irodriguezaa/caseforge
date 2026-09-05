"""Publication association for CaseForge Test Cases.

Keeps Zephyr/Jira IDs off the original TestCase row so coverage fields stay unmodified.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.test_case import TestCase


class TestCasePublication(Base):
    __tablename__ = "test_case_publications"
    __table_args__ = (
        UniqueConstraint("test_case_id", "destination", name="uq_test_case_publication_dest"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    test_case_id: Mapped[int] = mapped_column(
        ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False
    )
    destination: Mapped[str] = mapped_column(String(40), nullable=False, default="QCO")
    remote_key: Mapped[str | None] = mapped_column(String(40), nullable=True)
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    test_case: Mapped["TestCase"] = relationship()
