"""Epc ORM model.

One row per EPC/BRF detected in an RN Operativo. Persists BOTH the analyzer's read of the
document (epc_key, brf_key, titulo, alcance, nota_rte, estado_jira, qc_suggestion) AND the
user's own editable decisions: include_in_qc (Paso 4), alcance_funcional and
dispositivos_aplicables (Paso 3). Kept as separate fields on purpose (see qc_suggestion vs
include_in_qc below). Test-case generation is not built yet.
"""

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.operativa_release import OperativaRelease
    from app.models.release import Release


class QcSuggestion(str, enum.Enum):
    """What the analyzer suggested at analysis time -- a historical record of the automatic
    read, never recomputed after the fact. NEVER the actual inclusion decision itself; see
    Epc.include_in_qc for that. Kept intentionally coarse (3 values) so "ambiguous" cases are
    never silently folded into "include" or "exclude" -- they must surface for human review."""

    SUGERIDO_INCLUIR = "SUGERIDO_INCLUIR"
    SUGERIDO_EXCLUIR = "SUGERIDO_EXCLUIR"
    REQUIERE_REVISION = "REQUIERE_REVISION"


class Epc(Base):
    __tablename__ = "epcs"

    id: Mapped[int] = mapped_column(primary_key=True)
    operativa_release_id: Mapped[int] = mapped_column(
        ForeignKey("operativa_releases.id", ondelete="CASCADE"), nullable=False
    )
    # Frozen onto a QC Release at Paso 5 create time. Later include_in_qc edits on the
    # Operativa wizard must not add/remove rows here.
    release_id: Mapped[int | None] = mapped_column(
        ForeignKey("releases.id", ondelete="SET NULL"), nullable=True
    )

    # --- Lo que el analyzer leyó del documento, verbatim (Paso 4 muestra esto) ---
    brf_key: Mapped[str] = mapped_column(String(30), nullable=False)
    epc_key: Mapped[str | None] = mapped_column(String(30), nullable=True)
    titulo: Mapped[str] = mapped_column(Text, nullable=False)
    alcance: Mapped[str | None] = mapped_column(String(50), nullable=True)  # "Total" / "Parcial" / None si no se indicó
    nota_rte: Mapped[str | None] = mapped_column(Text, nullable=True)
    estado_jira: Mapped[str | None] = mapped_column(String(50), nullable=True)  # "In Validate" / "Done" / "In Develop" / etc.

    # --- Paso 4: sugerencia del sistema (histórica, no se recalcula) vs. decisión real del usuario ---
    qc_suggestion: Mapped[QcSuggestion] = mapped_column(
        Enum(QcSuggestion, name="qc_suggestion", native_enum=True, validate_strings=True),
        nullable=False,
    )
    include_in_qc: Mapped[bool] = mapped_column(Boolean, nullable=False)  # editable en cualquier momento, nunca definitivo

    # --- Paso 3: alcance funcional y dispositivos, manuales (nunca inferidos por analogía) ---
    alcance_funcional: Mapped[str | None] = mapped_column(Text, nullable=True)
    dispositivos_aplicables: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    operativa_release: Mapped["OperativaRelease"] = relationship(back_populates="epcs")
    release: Mapped["Release | None"] = relationship(back_populates="included_epcs")
