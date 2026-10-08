"""Jira ticket key on each Test Step (failure evidence).

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("test_steps", sa.Column("jira_ticket", sa.String(length=250), nullable=True))


def downgrade() -> None:
    op.drop_column("test_steps", "jira_ticket")
