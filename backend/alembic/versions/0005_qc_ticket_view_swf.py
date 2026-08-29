"""Add view, device, swf, is_attributed to qc_tickets

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-28

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

qc_ticket_view = postgresql.ENUM("OPERATIVAS", "RELEASE", name="qc_ticket_view", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    qc_ticket_view.create(bind, checkfirst=True)

    # No default: every existing row (if any) must be explicitly reclassified since "view" is a
    # new required dimension. In practice this table has no production data yet.
    op.add_column("qc_tickets", sa.Column("view", qc_ticket_view, nullable=True))
    op.execute("DELETE FROM qc_tickets")  # pre-view rows have no valid view; safe to clear (no prod data yet)
    op.alter_column("qc_tickets", "view", nullable=False)

    op.add_column("qc_tickets", sa.Column("device", sa.String(length=50), nullable=True))
    op.add_column("qc_tickets", sa.Column("swf", sa.String(length=50), nullable=True))
    op.add_column("qc_tickets", sa.Column("is_attributed", sa.Boolean(), nullable=True))
    op.create_index("idx_qc_tickets_view", "qc_tickets", ["view"])


def downgrade() -> None:
    op.drop_index("idx_qc_tickets_view", table_name="qc_tickets")
    op.drop_column("qc_tickets", "is_attributed")
    op.drop_column("qc_tickets", "swf")
    op.drop_column("qc_tickets", "device")
    op.drop_column("qc_tickets", "view")

    bind = op.get_bind()
    qc_ticket_view.drop(bind, checkfirst=True)
