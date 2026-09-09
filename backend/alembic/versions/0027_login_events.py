"""Append-only table for successful QC Pulse logins.

Revision ID: 0027
Revises: 0026
Create Date: 2026-09-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "login_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("logged_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_login_events_email", "login_events", ["email"])
    op.create_index("ix_login_events_logged_at", "login_events", ["logged_at"])


def downgrade() -> None:
    op.drop_index("ix_login_events_logged_at", table_name="login_events")
    op.drop_index("ix_login_events_email", table_name="login_events")
    op.drop_table("login_events")
