"""Store Operativa RN PDF path for TRI/context at generation time.

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-01

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "operativa_releases",
        sa.Column("pdf_file_path", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("operativa_releases", "pdf_file_path")
