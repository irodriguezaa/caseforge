"""QC-corrected matrix modules and template values on a Release.

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-12

Additive. Downgrade drops only these two columns.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: Union[str, None] = "0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("releases") as batch:
        batch.add_column(sa.Column("qc_matrix_touched_modules", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("qc_matrix_template_values", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("releases") as batch:
        batch.drop_column("qc_matrix_template_values")
        batch.drop_column("qc_matrix_touched_modules")
