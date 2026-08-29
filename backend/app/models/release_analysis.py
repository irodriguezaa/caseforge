"""ReleaseAnalysis ORM model for storing Release Note PDF analysis results."""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.release import Release


class ReleaseAnalysis(Base):
    """Stores structured analysis results extracted from a Release Note PDF.

    Desacoplado del futuro motor de generación QC basado en .md. Almacena metadatos del PDF,
    campos detectados, métricas extraídas y versión del motor (ej. 'v0.1').
    """

    __tablename__ = "release_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    release_id: Mapped[int | None] = mapped_column(
        ForeignKey("releases.id", ondelete="CASCADE"), nullable=True, index=True
    )
    pdf_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    pdf_file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    detected_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    detected_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    detected_platform: Mapped[str | None] = mapped_column(String(50), nullable=True)
    detected_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    features_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    qa_qc_issues_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    nco_issues_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    detected_devices: Mapped[str | None] = mapped_column(String(255), nullable=True)
    proposed_coverage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimation_text: Mapped[str | None] = mapped_column(String(200), nullable=True)

    observations: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    raw_analysis: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    qc_engine_version: Mapped[str] = mapped_column(String(50), default="v0.1", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    release: Mapped["Release | None"] = relationship("Release", back_populates="analyses")
