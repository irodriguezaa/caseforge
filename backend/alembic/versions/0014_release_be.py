"""Release BE draft, applicable-case placeholders, and link from QC Release.

Does not alter 0009–0013.

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-31

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "be_releases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("entregable", sa.String(length=200), nullable=True),
        sa.Column("swf", sa.String(length=50), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("pdf_filename", sa.String(length=255), nullable=True),
        sa.Column("regresivo_scope", sa.String(length=20), nullable=True),
        sa.Column("affected_component", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

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

    op.add_column("releases", sa.Column("be_release_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_releases_be_release_id",
        "releases",
        "be_releases",
        ["be_release_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint("uq_releases_be_release_id", "releases", ["be_release_id"])


def downgrade() -> None:
    op.drop_constraint("uq_releases_be_release_id", "releases", type_="unique")
    op.drop_constraint("fk_releases_be_release_id", "releases", type_="foreignkey")
    op.drop_column("releases", "be_release_id")
    op.drop_index("idx_be_applicable_cases_release_id", table_name="be_applicable_cases")
    op.drop_index("idx_be_applicable_cases_be_release_id", table_name="be_applicable_cases")
    op.drop_table("be_applicable_cases")
    op.drop_table("be_releases")
