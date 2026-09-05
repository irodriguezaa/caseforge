"""TestCase ORM model.

test_case_id (e.g. "QC-001") is a QC-readable label, unique per release, NOT the primary key.
The primary key is the internal `id` column, independent of the release-scoped label.
"""

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.defect import Defect
    from app.models.release import Release
    from app.models.test_step import TestStep
    from app.models.window import OperationalWindow, ReleaseWindow


class TestCasePriority(str, enum.Enum):
    """Severity/priority scale used across CaseForge's QC standard: exactly Blocker and Critical."""

    BLOCKER = "BLOCKER"
    CRITICAL = "CRITICAL"


class TestCaseType(str, enum.Enum):
    FUNCTIONAL = "FUNCTIONAL"
    REGRESSION = "REGRESSION"
    SMOKE = "SMOKE"
    UI = "UI"
    PERFORMANCE = "PERFORMANCE"
    OTHER = "OTHER"


class TestCaseStatus(str, enum.Enum):
    UNEXECUTED = "UNEXECUTED"
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    N_A = "N_A"


class TestCase(Base):
    """A QC test case belonging to exactly one Release. Owns many TestStep rows."""

    __tablename__ = "test_cases"
    __table_args__ = (
        # test_case_id (e.g. "QC-001") is unique PER RELEASE, not globally.
        UniqueConstraint("release_id", "test_case_id", name="uq_test_case_release_test_case_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    release_id: Mapped[int] = mapped_column(
        ForeignKey("releases.id", ondelete="CASCADE"), nullable=False
    )
    test_case_id: Mapped[str] = mapped_column(String(20), nullable=False)
    component: Mapped[str] = mapped_column(String(150), nullable=False)
    test_case_name: Mapped[str] = mapped_column(String(250), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Independent, optional associations -- no hierarchy between the two window types.
    operational_window_id: Mapped[int | None] = mapped_column(
        ForeignKey("operational_windows.id", ondelete="SET NULL"), nullable=True
    )
    release_window_id: Mapped[int | None] = mapped_column(
        ForeignKey("release_windows.id", ondelete="SET NULL"), nullable=True
    )
    priority: Mapped[TestCasePriority] = mapped_column(
        Enum(TestCasePriority, name="test_case_priority", native_enum=True, validate_strings=True),
        nullable=False,
        default=TestCasePriority.CRITICAL,
        server_default=TestCasePriority.CRITICAL.value,
    )
    test_type: Mapped[TestCaseType] = mapped_column(
        Enum(TestCaseType, name="test_case_type", native_enum=True, validate_strings=True),
        nullable=False,
        default=TestCaseType.FUNCTIONAL,
        server_default=TestCaseType.FUNCTIONAL.value,
    )
    status: Mapped[TestCaseStatus] = mapped_column(
        Enum(TestCaseStatus, name="test_case_status", native_enum=True, validate_strings=True),
        nullable=False,
        default=TestCaseStatus.UNEXECUTED,
        server_default=TestCaseStatus.UNEXECUTED.value,
    )
    test_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    requires_condition: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    technical_epic: Mapped[str | None] = mapped_column(String(250), nullable=True)
    technical_story: Mapped[str | None] = mapped_column(String(500), nullable=True)
    scenario_origin: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_rn: Mapped[str | None] = mapped_column(String(250), nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    complexity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    estimation_hours: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    generated_by_engine: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    ecosystem: Mapped[str | None] = mapped_column(String(16), nullable=True)
    device: Mapped[str | None] = mapped_column(String(80), nullable=True)
    device_source: Mapped[str | None] = mapped_column(String(250), nullable=True)
    applicability_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    duplicate_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    group_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    hn_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    release: Mapped["Release"] = relationship(back_populates="test_cases")
    steps: Mapped[list["TestStep"]] = relationship(
        back_populates="test_case",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="TestStep.step_number",
    )
    operational_window: Mapped["OperationalWindow | None"] = relationship(back_populates="test_cases")
    release_window: Mapped["ReleaseWindow | None"] = relationship(back_populates="test_cases")
    defects: Mapped[list["Defect"]] = relationship(
        back_populates="test_case", cascade="all, delete-orphan", passive_deletes=True
    )
