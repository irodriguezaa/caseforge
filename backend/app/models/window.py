"""OperationalWindow and ReleaseWindow ORM models.

Per product decision: these are two INDEPENDENT entities, not a hierarchy. A TestCase may be
associated with an OperationalWindow, a ReleaseWindow, both, or neither -- there is no FK between
OperationalWindow and ReleaseWindow themselves.
"""

import enum
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.release import Release
    from app.models.test_case import TestCase


class WindowStatus(str, enum.Enum):
    PLANNED = "PLANNED"
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


class OperationalWindow(Base):
    """A QC operational time block (e.g. a week of testing activity), independent of any single
    Release. May span multiple Releases and Clusters via the TestCases associated with it."""

    __tablename__ = "operational_windows"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    cluster: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[WindowStatus] = mapped_column(
        Enum(WindowStatus, name="window_status", native_enum=True, validate_strings=True),
        nullable=False,
        default=WindowStatus.PLANNED,
        server_default=WindowStatus.PLANNED.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    test_cases: Mapped[list["TestCase"]] = relationship(back_populates="operational_window")


class ReleaseWindow(Base):
    """The execution schedule for one Release (e.g. "Release 8.15 - Regresión completa")."""

    __tablename__ = "release_windows"

    id: Mapped[int] = mapped_column(primary_key=True)
    release_id: Mapped[int] = mapped_column(ForeignKey("releases.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[WindowStatus] = mapped_column(
        Enum(WindowStatus, name="window_status", native_enum=True, validate_strings=True),
        nullable=False,
        default=WindowStatus.PLANNED,
        server_default=WindowStatus.PLANNED.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    release: Mapped["Release"] = relationship()
    test_cases: Mapped[list["TestCase"]] = relationship(back_populates="release_window")
