"""Add multi-cluster JSON column on be_releases.

Historical rows stay NULL. Does not change releases.cluster used by Apps/Operativas.

Revision ID: 0025
Revises: 0024
Create Date: 2026-09-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("be_releases", sa.Column("clusters", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("be_releases", "clusters")
