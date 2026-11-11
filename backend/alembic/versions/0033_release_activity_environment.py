"""Release Tipo and Ambiente for the Jira EPC.

Revision ID: 0033
Revises: 0032
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: Union[str, None] = "0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("releases") as batch:
        batch.add_column(sa.Column("activity_type", sa.String(length=30), nullable=True))
        batch.add_column(sa.Column("environment", sa.String(length=10), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("releases") as batch:
        batch.drop_column("environment")
        batch.drop_column("activity_type")
