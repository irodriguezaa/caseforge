"""Add description to operativa_releases (Paso 2 Información del RN).

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-31

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("operativa_releases", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("operativa_releases", "description")
