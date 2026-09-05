"""Drop be_applicable_cases — test cases for Release BE live on the QC Release after create.

0014 is left unchanged (Alembic integrity). This revision removes the unused case-placeholder
table now that Matriz QC is not selected in the wizard.

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-31

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("idx_be_applicable_cases_release_id", table_name="be_applicable_cases")
    op.drop_index("idx_be_applicable_cases_be_release_id", table_name="be_applicable_cases")
    op.drop_table("be_applicable_cases")


def downgrade() -> None:
    op.create_table(
        "be_applicable_cases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("be_release_id", sa.Integer(), nullable=False),
        sa.Column("release_id", sa.Integer(), nullable=True),
        sa.Column("case_key", sa.String(length=50), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("component", sa.String(length=150), nullable=True),
        sa.Column("include_in_qc", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["be_release_id"], ["be_releases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["release_id"], ["releases.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_be_applicable_cases_be_release_id", "be_applicable_cases", ["be_release_id"])
    op.create_index("idx_be_applicable_cases_release_id", "be_applicable_cases", ["release_id"])
