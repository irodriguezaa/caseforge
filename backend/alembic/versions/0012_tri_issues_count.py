"""Add tri_issues_count to release_analyses

Re-created after 0008_tri_issues_count.py was found to have never reached the real repo (file
never existed there, column never applied). Rather than retroactively inserting a "0008" between
0007 and 0009 -- the real DB already advanced past that point via 0009/0010/0011 without it --
this adds the same column as a new migration at the current head. Confirmed no conflict: 0010
and 0011 only touch operativa_releases, never release_analyses.

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-31

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "release_analyses",
        sa.Column("tri_issues_count", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("release_analyses", "tri_issues_count")
