"""Defect ORM model: minimal entity added to support QC Dashboard defect metrics.

Scoped deliberately small for this sprint: a Defect belongs to exactly one TestCase, carries a
title/description/severity/status, and nothing else (no Jira linkage yet -- that stays out of
scope per the original Sprint 2 constraints).
"""

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.test_case import TestCasePriority

if TYPE_CHECKING:
    from app.models.test_case import TestCase


class DefectStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class Defect(Base):
    __tablename__ = "defects"

    id: Mapped[int] = mapped_column(primary_key=True)
    test_case_id: Mapped[int] = mapped_column(
        ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Reuses the same Blocker/Critical severity scale as TestCase.priority for consistency.
    severity: Mapped[TestCasePriority] = mapped_column(
        Enum(TestCasePriority, name="test_case_priority", native_enum=True, validate_strings=True),
        nullable=False,
    )
    status: Mapped[DefectStatus] = mapped_column(
        Enum(DefectStatus, name="defect_status", native_enum=True, validate_strings=True),
        nullable=False,
        default=DefectStatus.OPEN,
        server_default=DefectStatus.OPEN.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    test_case: Mapped["TestCase"] = relationship(back_populates="defects")
