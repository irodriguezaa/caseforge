"""Add qc_tickets (independent defect radar, not linked to Release/TestCase/Defect)

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-28

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

qc_ticket_priority = postgresql.ENUM(
    "BLOCKER", "CRITICAL", "OTHER", name="qc_ticket_priority", create_type=False
)
qc_ticket_source = postgresql.ENUM(
    "QC_DETECTED", "LEAKED", name="qc_ticket_source", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    qc_ticket_priority.create(bind, checkfirst=True)
    qc_ticket_source.create(bind, checkfirst=True)

    op.create_table(
        "qc_tickets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("issue_key", sa.String(length=50), nullable=False),
        sa.Column("issue_type", sa.String(length=100), nullable=True),
        sa.Column("project_key", sa.String(length=50), nullable=True),
        sa.Column("priority_bucket", qc_ticket_priority, nullable=False),
        sa.Column("status_raw", sa.String(length=100), nullable=False),
        sa.Column("is_open", sa.Boolean(), nullable=False),
        sa.Column("source", qc_ticket_source, nullable=False),
        sa.Column("cluster", sa.String(length=50), nullable=True),
        sa.Column("affected_program", sa.String(length=150), nullable=True),
        sa.Column("created_date", sa.Date(), nullable=False),
        sa.Column("resolved_date", sa.Date(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "imported_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("issue_key", name="uq_qc_ticket_issue_key"),
    )
    op.create_index("idx_qc_tickets_cluster", "qc_tickets", ["cluster"])
    op.create_index("idx_qc_tickets_source", "qc_tickets", ["source"])
    op.create_index("idx_qc_tickets_created_date", "qc_tickets", ["created_date"])


def downgrade() -> None:
    op.drop_index("idx_qc_tickets_created_date", table_name="qc_tickets")
    op.drop_index("idx_qc_tickets_source", table_name="qc_tickets")
    op.drop_index("idx_qc_tickets_cluster", table_name="qc_tickets")
    op.drop_table("qc_tickets")

    bind = op.get_bind()
    qc_ticket_source.drop(bind, checkfirst=True)
    qc_ticket_priority.drop(bind, checkfirst=True)
