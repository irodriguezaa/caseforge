"""Associate Zephyr/Jira Test keys with CaseForge TCs without mutating coverage fields.

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "test_case_publications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("test_case_id", sa.Integer(), sa.ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("destination", sa.String(length=40), nullable=False),
        sa.Column("remote_key", sa.String(length=40), nullable=True),
        sa.Column("result", sa.String(length=20), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("test_case_id", "destination", name="uq_test_case_publication_dest"),
    )


def downgrade() -> None:
    op.drop_table("test_case_publications")
