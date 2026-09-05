"""QcTicket ORM model.

Fully independent of Release/TestCase/Defect (per product decision): this is a general QC
defect-radar entity fed from Jira exports (CSV today, Jira API later), covering ALL QC ticket
volume across operational windows and releases -- not tied to a specific Release's Test Cases.
"""

import enum
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class QcTicketPriority(str, enum.Enum):
    """Distinct from TestCasePriority: real Jira data includes a third 'Otros' bucket that
    doesn't apply to CaseForge's own Test Case severity scale."""

    BLOCKER = "BLOCKER"
    CRITICAL = "CRITICAL"
    OTHER = "OTHER"


class QcTicketView(str, enum.Enum):
    """The two dashboard views this ticket belongs to -- orthogonal to source (QC_DETECTED vs
    LEAKED). Together they map 1:1 to the 4 real Jira filters (112929/113062/113261/113784)."""

    OPERATIVAS = "OPERATIVAS"
    RELEASE = "RELEASE"


class QcTicketSource(str, enum.Enum):
    """Set by which upload the ticket came from (or which Jira filter, once that exists) --
    not a column in the Jira export itself."""

    QC_DETECTED = "QC_DETECTED"
    LEAKED = "LEAKED"


class QcTicket(Base):
    __tablename__ = "qc_tickets"
    __table_args__ = (
        UniqueConstraint("issue_key", "view", "source", name="uq_qc_ticket_issue_key_view_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    issue_key: Mapped[str] = mapped_column(String(50), nullable=False)
    issue_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    project_key: Mapped[str | None] = mapped_column(String(50), nullable=True)
    priority_bucket: Mapped[QcTicketPriority] = mapped_column(
        Enum(QcTicketPriority, name="qc_ticket_priority", native_enum=True, validate_strings=True),
        nullable=False,
    )
    status_raw: Mapped[str] = mapped_column(String(100), nullable=False)
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False)
    view: Mapped[QcTicketView] = mapped_column(
        Enum(QcTicketView, name="qc_ticket_view", native_enum=True, validate_strings=True),
        nullable=False,
    )
    source: Mapped[QcTicketSource] = mapped_column(
        Enum(QcTicketSource, name="qc_ticket_source", native_enum=True, validate_strings=True),
        nullable=False,
    )
    # Normalized to the same 5-value vocabulary Release.cluster uses (AUP/Andina/CENAM/
    # Dominicana/Global); "Mexico" and similar are folded into Global at import time.
    # Only meaningful for view=OPERATIVAS -- Jira's Cluster field isn't used for Release.
    cluster: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Raw "Campo personalizado (Programa Afectado)" (Operativas only).
    affected_program: Mapped[str | None] = mapped_column(String(150), nullable=True)
    # Computed device/SWF classification -- Operativas via affected_program + created_date
    # (PRE/POST cutoff), Release via project_key prefix. See services/qc_ticket_imports.py for
    # the exact mapping tables, extracted verbatim from the QC team's reference tool.
    device: Mapped[str | None] = mapped_column(String(50), nullable=True)
    swf: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Release + LEAKED only: whether this leaked ticket already had a QC/QA Bug linked (via any
    # Jira link type) before it derived into a production issue -- if so, it's NOT a genuine
    # leak (QA/QC had already caught it). Null for anything that isn't Release+LEAKED.
    is_attributed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_date: Mapped[date] = mapped_column(Date, nullable=False)
    resolved_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
