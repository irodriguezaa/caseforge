"""Published QC base matrices (OTT / IPTV) and their versions.

A Release may point at the version it was built with. Publishing another version
does not move that pointer.
"""

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db import Base

if TYPE_CHECKING:
    from app.models.release import Release


class QcMatrixVersion(Base):
    __tablename__ = "qc_matrix_versions"
    __table_args__ = (UniqueConstraint("code", "version", name="uq_qc_matrix_code_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", server_default="draft")
    generated_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    providers: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    scope_rules: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    modules: Mapped[list["QcMatrixModule"]] = relationship(
        back_populates="matrix_version", cascade="all, delete-orphan", passive_deletes=True
    )
    devices: Mapped[list["QcMatrixDevice"]] = relationship(
        back_populates="matrix_version", cascade="all, delete-orphan", passive_deletes=True
    )
    cases: Mapped[list["QcMatrixCase"]] = relationship(
        back_populates="matrix_version", cascade="all, delete-orphan", passive_deletes=True
    )
    releases: Mapped[list["Release"]] = relationship(back_populates="qc_matrix_version")


class QcMatrixModule(Base):
    __tablename__ = "qc_matrix_modules"
    __table_args__ = (UniqueConstraint("matrix_version_id", "module_key", name="uq_qc_matrix_module_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    matrix_version_id: Mapped[int] = mapped_column(
        ForeignKey("qc_matrix_versions.id", ondelete="CASCADE"), nullable=False
    )
    module_key: Mapped[str] = mapped_column(String(64), nullable=False)
    group_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    matrix_version: Mapped[QcMatrixVersion] = relationship(back_populates="modules")
    relations: Mapped[list["QcMatrixModuleLink"]] = relationship(
        back_populates="module", cascade="all, delete-orphan", passive_deletes=True
    )
    cases: Mapped[list["QcMatrixCase"]] = relationship(back_populates="module")


class QcMatrixModuleLink(Base):
    __tablename__ = "qc_matrix_module_links"
    __table_args__ = (UniqueConstraint("module_id", "related_key", name="uq_qc_matrix_module_related"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    module_id: Mapped[int] = mapped_column(
        ForeignKey("qc_matrix_modules.id", ondelete="CASCADE"), nullable=False
    )
    related_key: Mapped[str] = mapped_column(String(64), nullable=False)

    module: Mapped[QcMatrixModule] = relationship(back_populates="relations")


class QcMatrixDevice(Base):
    __tablename__ = "qc_matrix_devices"
    __table_args__ = (UniqueConstraint("matrix_version_id", "code", name="uq_qc_matrix_device_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    matrix_version_id: Mapped[int] = mapped_column(
        ForeignKey("qc_matrix_versions.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    screen: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    mdp_mx: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    mdp_other_regions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    matrix_version: Mapped[QcMatrixVersion] = relationship(back_populates="devices")
    case_links: Mapped[list["QcMatrixCaseDevice"]] = relationship(
        back_populates="device", cascade="all, delete-orphan", passive_deletes=True
    )


class QcMatrixCase(Base):
    __tablename__ = "qc_matrix_cases"
    __table_args__ = (UniqueConstraint("matrix_version_id", "base_id", name="uq_qc_matrix_case_base_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    matrix_version_id: Mapped[int] = mapped_column(
        ForeignKey("qc_matrix_versions.id", ondelete="CASCADE"), nullable=False
    )
    base_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    module_id: Mapped[int | None] = mapped_column(
        ForeignKey("qc_matrix_modules.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    steps: Mapped[str] = mapped_column(Text, nullable=False, default="")
    expected: Mapped[str] = mapped_column(Text, nullable=False, default="")
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="Critical")
    smoke: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    region: Mapped[str | None] = mapped_column(String(40), nullable=True)
    parametrized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    param_values: Mapped[str] = mapped_column(Text, nullable=False, default="")
    user_types: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    providers_in_source: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    case_status: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    sources: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    origin: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ott_equivalent: Mapped[str] = mapped_column(Text, nullable=False, default="")
    review_reasons: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    approvals: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    matrix_version: Mapped[QcMatrixVersion] = relationship(back_populates="cases")
    module: Mapped[QcMatrixModule | None] = relationship(back_populates="cases")
    device_links: Mapped[list["QcMatrixCaseDevice"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", passive_deletes=True
    )


class QcMatrixCaseDevice(Base):
    __tablename__ = "qc_matrix_case_devices"
    __table_args__ = (UniqueConstraint("case_id", "device_id", name="uq_qc_matrix_case_device"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("qc_matrix_cases.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[int] = mapped_column(
        ForeignKey("qc_matrix_devices.id", ondelete="CASCADE"), nullable=False
    )
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")

    case: Mapped[QcMatrixCase] = relationship(back_populates="device_links")
    device: Mapped[QcMatrixDevice] = relationship(back_populates="case_links")
