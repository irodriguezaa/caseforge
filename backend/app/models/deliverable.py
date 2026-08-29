"""Deliverable ORM model.

A Deliverable groups the QC version history of one functional unit (e.g. "CV WEB -
Funcionalidad X") across multiple Releases: one Evolutivo plus zero or more Revalidaciones.
Get-or-create by name is handled in routers/releases.py, not here -- this model stays a plain
entity with no business logic of its own.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.release import Release


class Deliverable(Base):
    __tablename__ = "deliverables"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    releases: Mapped[list["Release"]] = relationship(back_populates="deliverable")
