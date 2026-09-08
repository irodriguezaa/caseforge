"""BeRelease ORM model.

Draft for the Release BE wizard (regresivos de backend). Analog to OperativaRelease, but a
separate table and flow: optional RN metadata and regresivo scope. Test cases are created on
the QC Release after Paso 4, not selected in the wizard.
"""

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.release import Release


class BeRelease(Base):
    __tablename__ = "be_releases"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    entregable: Mapped[str | None] = mapped_column(String(200), nullable=True)
    swf: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # JSON list: ["Todos"] or one-or-more of Global/AUP/CENAM/Andina/Dominicana. Not a sixth cluster.
    clusters: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Optional: some BE regresivos arrive with no Release Note.
    pdf_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # COMPLETO | SMOKE | ACOTADO — stored as text (not Release.validation_type).
    regresivo_scope: Mapped[str | None] = mapped_column(String(20), nullable=True)
    affected_component: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Paso 3: ventana QC (mismos campos que Operativa / Apps). Días hábiles se calculan al crear el QC Release.
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    qc_release: Mapped["Release | None"] = relationship(
        back_populates="be_release", uselist=False
    )
