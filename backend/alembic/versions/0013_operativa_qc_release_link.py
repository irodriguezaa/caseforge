"""Link QC Release rows created from an Operativa to the source OperativaRelease and freeze
included EPCs onto that Release (epcs.release_id). Does not alter 0009–0012.

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-31

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("releases", sa.Column("operativa_release_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_releases_operativa_release_id",
        "releases",
        "operativa_releases",
        ["operativa_release_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint("uq_releases_operativa_release_id", "releases", ["operativa_release_id"])

    op.add_column("epcs", sa.Column("release_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_epcs_release_id",
        "epcs",
        "releases",
        ["release_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_epcs_release_id", "epcs", ["release_id"])


def downgrade() -> None:
    op.drop_index("idx_epcs_release_id", table_name="epcs")
    op.drop_constraint("fk_epcs_release_id", "epcs", type_="foreignkey")
    op.drop_column("epcs", "release_id")
    op.drop_constraint("uq_releases_operativa_release_id", "releases", type_="unique")
    op.drop_constraint("fk_releases_operativa_release_id", "releases", type_="foreignkey")
    op.drop_column("releases", "operativa_release_id")
