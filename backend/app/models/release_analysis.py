"""ReleaseAnalysis ORM model.

NOTE: this file's exact content was NOT provided verbatim by the user (unlike the other 11
files reconstructed this session) -- it is inferred from migration 0006's column list and how
it's referenced in routers/releases.py / schemas/release.py. It is used here only so the
sandbox can import app.models and run pytest; it is not part of the Deliverable/Revalidation
deliverable and is flagged to the user rather than silently assumed identical to their real file.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.release import Release


class ReleaseAnalysis(Base):
    __tablename__ = "release_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    release_id: Mapped[int | None] = mapped_column(
        ForeignKey("releases.id", ondelete="CASCADE"), nullable=True
    )
    pdf_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    pdf_file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    detected_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    detected_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    detected_platform: Mapped[str | None] = mapped_column(String(50), nullable=True)
    detected_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    features_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    qa_qc_issues_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    nco_issues_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    tri_issues_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    detected_devices: Mapped[str | None] = mapped_column(String(255), nullable=True)
    proposed_coverage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimation_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    observations: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    raw_analysis: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    qc_engine_version: Mapped[str] = mapped_column(
        String(50), nullable=False, default="v0.1", server_default="v0.1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    release: Mapped["Release | None"] = relationship(back_populates="analyses")
