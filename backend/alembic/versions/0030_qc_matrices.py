"""QC base matrices (OTT/IPTV) and the version a Release was built with.

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-12

Additive. Downgrade drops only the tables and column created here.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: Union[str, None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "qc_matrix_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("generated_on", sa.Date(), nullable=True),
        sa.Column("providers", sa.JSON(), nullable=False),
        sa.Column("scope_rules", sa.JSON(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("code", "version", name="uq_qc_matrix_code_version"),
    )
    op.create_table(
        "qc_matrix_modules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("matrix_version_id", sa.Integer(), nullable=False),
        sa.Column("module_key", sa.String(length=64), nullable=False),
        sa.Column("group_name", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("name", sa.String(length=250), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["matrix_version_id"], ["qc_matrix_versions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("matrix_version_id", "module_key", name="uq_qc_matrix_module_key"),
    )
    op.create_table(
        "qc_matrix_module_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("module_id", sa.Integer(), nullable=False),
        sa.Column("related_key", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["module_id"], ["qc_matrix_modules.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("module_id", "related_key", name="uq_qc_matrix_module_related"),
    )
    op.create_table(
        "qc_matrix_devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("matrix_version_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("screen", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("mdp_mx", sa.JSON(), nullable=False),
        sa.Column("mdp_other_regions", sa.JSON(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["matrix_version_id"], ["qc_matrix_versions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("matrix_version_id", "code", name="uq_qc_matrix_device_code"),
    )
    op.create_table(
        "qc_matrix_cases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("matrix_version_id", sa.Integer(), nullable=False),
        sa.Column("base_id", sa.String(length=80), nullable=True),
        sa.Column("module_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("steps", sa.Text(), nullable=False, server_default=""),
        sa.Column("expected", sa.Text(), nullable=False, server_default=""),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="Critical"),
        sa.Column("smoke", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("region", sa.String(length=40), nullable=True),
        sa.Column("parametrized", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("param_values", sa.Text(), nullable=False, server_default=""),
        sa.Column("user_types", sa.JSON(), nullable=False),
        sa.Column("providers_in_source", sa.JSON(), nullable=False),
        sa.Column("case_status", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("origin", sa.Text(), nullable=False, server_default=""),
        sa.Column("ott_equivalent", sa.Text(), nullable=False, server_default=""),
        sa.Column("review_reasons", sa.JSON(), nullable=False),
        sa.Column("approvals", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["matrix_version_id"], ["qc_matrix_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["module_id"], ["qc_matrix_modules.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("matrix_version_id", "base_id", name="uq_qc_matrix_case_base_id"),
    )
    op.create_table(
        "qc_matrix_case_devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("case_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["case_id"], ["qc_matrix_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["device_id"], ["qc_matrix_devices.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("case_id", "device_id", name="uq_qc_matrix_case_device"),
    )
    with op.batch_alter_table("releases") as batch:
        batch.add_column(sa.Column("qc_matrix_version_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_releases_qc_matrix_version_id",
            "qc_matrix_versions",
            ["qc_matrix_version_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("releases") as batch:
        batch.drop_constraint("fk_releases_qc_matrix_version_id", type_="foreignkey")
        batch.drop_column("qc_matrix_version_id")
    op.drop_table("qc_matrix_case_devices")
    op.drop_table("qc_matrix_cases")
    op.drop_table("qc_matrix_devices")
    op.drop_table("qc_matrix_module_links")
    op.drop_table("qc_matrix_modules")
    op.drop_table("qc_matrix_versions")
