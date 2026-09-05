"""Separate TestCase component / ecosystem / device.

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-02

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("test_cases", sa.Column("ecosystem", sa.String(length=16), nullable=True))
    op.add_column("test_cases", sa.Column("device", sa.String(length=80), nullable=True))
    op.add_column("test_cases", sa.Column("device_source", sa.String(length=250), nullable=True))
    op.add_column("test_cases", sa.Column("applicability_reason", sa.Text(), nullable=True))
    op.add_column("test_cases", sa.Column("duplicate_status", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("test_cases", "duplicate_status")
    op.drop_column("test_cases", "applicability_reason")
    op.drop_column("test_cases", "device_source")
    op.drop_column("test_cases", "device")
    op.drop_column("test_cases", "ecosystem")
