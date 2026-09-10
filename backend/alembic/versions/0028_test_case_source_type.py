"""App RN Type column (Funcionalidad / NCO / QA Bug / QC Bug / TRI).

Revision ID: 0028
Revises: 0027
Create Date: 2026-09-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("test_cases", sa.Column("source_type", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("test_cases", "source_type")
