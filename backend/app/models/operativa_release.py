"""OperativaRelease ORM model.

The uploaded Release Note Operativo. Groups the EPCs detected within it -- analog to how
Deliverable groups Release history, but for the RN Operativo -> EPC -> test cases pipeline
(a separate flow from the device-based Release pipeline; see app/services/operativa_analyzer.py).
"""

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.epc import Epc
    from app.models.release import Release


class OperativaRelease(Base):
    __tablename__ = "operativa_releases"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Paso 2: extracted from the RN when evidence is clear; never defaulted to the filename.
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    entregable: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cluster: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    pdf_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    pdf_file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Paso 3: QC configuration. No QC-resource columns on this model.
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    jira_filter_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    jira_filter_manual: Mapped[str | None] = mapped_column(Text, nullable=True)
    instrucciones_adicionales: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    epcs: Mapped[list["Epc"]] = relationship(
        back_populates="operativa_release", cascade="all, delete-orphan", passive_deletes=True
    )
    qc_release: Mapped["Release | None"] = relationship(
        back_populates="operativa_release", uselist=False
    )
