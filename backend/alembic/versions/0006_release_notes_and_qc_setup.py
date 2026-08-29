"""Add release operational QC setup fields and release_analyses table

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-28

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add QC setup fields to releases table
    op.add_column("releases", sa.Column("start_date", sa.Date(), nullable=True))
    op.add_column("releases", sa.Column("end_date", sa.Date(), nullable=True))
    op.add_column("releases", sa.Column("qc_resources", sa.Integer(), nullable=True))
    op.add_column("releases", sa.Column("execution_days", sa.Integer(), nullable=True))
    op.add_column("releases", sa.Column("validation_type", sa.String(length=50), nullable=True))
    op.add_column("releases", sa.Column("jira_issue_filter", sa.Text(), nullable=True))

    # Create release_analyses table
    op.create_table(
        "release_analyses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("release_id", sa.Integer(), nullable=True),
        sa.Column("pdf_filename", sa.String(length=255), nullable=False),
        sa.Column("pdf_file_path", sa.String(length=500), nullable=True),
        sa.Column("detected_name", sa.String(length=200), nullable=True),
        sa.Column("detected_version", sa.String(length=50), nullable=True),
        sa.Column("detected_platform", sa.String(length=50), nullable=True),
        sa.Column("detected_description", sa.Text(), nullable=True),
        sa.Column("features_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("qa_qc_issues_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("nco_issues_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("detected_devices", sa.String(length=255), nullable=True),
        sa.Column("proposed_coverage", sa.Integer(), nullable=True),
        sa.Column("estimation_text", sa.String(length=200), nullable=True),
        sa.Column("observations", sa.JSON(), nullable=False),
        sa.Column("raw_analysis", sa.JSON(), nullable=False),
        sa.Column("qc_engine_version", sa.String(length=50), server_default="v0.1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["release_id"], ["releases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_release_analyses_release_id", "release_analyses", ["release_id"])


def downgrade() -> None:
    op.drop_index("idx_release_analyses_release_id", table_name="release_analyses")
    op.drop_table("release_analyses")

    op.drop_column("releases", "jira_issue_filter")
    op.drop_column("releases", "validation_type")
    op.drop_column("releases", "execution_days")
    op.drop_column("releases", "qc_resources")
    op.drop_column("releases", "end_date")
    op.drop_column("releases", "start_date")
