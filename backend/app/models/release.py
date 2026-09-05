"""Release ORM model."""

import enum
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.be_release import BeRelease
    from app.models.deliverable import Deliverable
    from app.models.epc import Epc
    from app.models.operativa_release import OperativaRelease
    from app.models.release_analysis import ReleaseAnalysis
    from app.models.test_case import TestCase


class ReleaseStatus(str, enum.Enum):
    """Lifecycle of a QC release.

    DRAFT is the only status that allows hard deletion (see routers/releases.py). Every other
    status must transition to CANCELLED instead of being deleted, since it may already have
    associated QC activity.
    """

    DRAFT = "DRAFT"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class ReleaseType(str, enum.Enum):
    """Distinguishes a fresh feature cycle from a re-test of a prior one, within a Deliverable.

    Orthogonal to ReleaseStatus (which tracks whether QC has *finished* the cycle) -- this
    tracks *why* the cycle exists at all. Nullable at the DB level so existing Releases that
    predate this concept aren't forced into a classification nobody made."""

    NUEVO = "NUEVO"
    EVOLUTIVO = "EVOLUTIVO"
    REVALIDACION = "REVALIDACION"


class Release(Base):
    """A QC release/testing cycle. Owns many TestCase rows and optional ReleaseAnalysis artifacts."""

    __tablename__ = "releases"
    __table_args__ = (
        UniqueConstraint("name", "version", "platform", name="uq_release_name_version_platform"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    cluster: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[ReleaseStatus] = mapped_column(
        Enum(ReleaseStatus, name="release_status", native_enum=True, validate_strings=True),
        nullable=False,
        default=ReleaseStatus.DRAFT,
        server_default=ReleaseStatus.DRAFT.value,
    )
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    qc_resources: Mapped[int | None] = mapped_column(Integer, nullable=True)
    execution_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    validation_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    jira_issue_filter: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Deliverable / lineage (Entregable, Tipo de Release, Release origen) ---
    deliverable_id: Mapped[int | None] = mapped_column(
        ForeignKey("deliverables.id", ondelete="SET NULL"), nullable=True
    )
    release_type: Mapped[ReleaseType | None] = mapped_column(
        Enum(ReleaseType, name="release_type", native_enum=True, validate_strings=True),
        nullable=True,
    )
    parent_release_id: Mapped[int | None] = mapped_column(
        ForeignKey("releases.id", ondelete="SET NULL"), nullable=True
    )
    # Set when this QC Release was created from an Operativa (one Operativa → one Release).
    operativa_release_id: Mapped[int | None] = mapped_column(
        ForeignKey("operativa_releases.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    be_release_id: Mapped[int | None] = mapped_column(
        ForeignKey("be_releases.id", ondelete="SET NULL"), nullable=True, unique=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    test_cases: Mapped[list["TestCase"]] = relationship(
        back_populates="release",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="TestCase.test_case_id",
    )
    analyses: Mapped[list["ReleaseAnalysis"]] = relationship(
        back_populates="release",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ReleaseAnalysis.created_at.desc()",
    )
    deliverable: Mapped["Deliverable | None"] = relationship(back_populates="releases")
    parent: Mapped["Release | None"] = relationship(remote_side=[id], back_populates="children")
    children: Mapped[list["Release"]] = relationship(back_populates="parent")
    operativa_release: Mapped["OperativaRelease | None"] = relationship(back_populates="qc_release")
    included_epcs: Mapped[list["Epc"]] = relationship(back_populates="release")
    be_release: Mapped["BeRelease | None"] = relationship(back_populates="qc_release")
