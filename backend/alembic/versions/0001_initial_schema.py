"""Initial Sprint 2 schema: releases, test_cases, test_steps

Revision ID: 0001
Revises:
Create Date: 2026-08-27

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

release_status = postgresql.ENUM(
    "DRAFT", "IN_PROGRESS", "COMPLETED", "CANCELLED", name="release_status", create_type=False
)
test_case_priority = postgresql.ENUM(
    "BLOCKER", "CRITICAL", name="test_case_priority", create_type=False
)
test_case_type = postgresql.ENUM(
    "FUNCTIONAL",
    "REGRESSION",
    "SMOKE",
    "UI",
    "PERFORMANCE",
    "OTHER",
    name="test_case_type",
    create_type=False,
)
test_case_status = postgresql.ENUM(
    "UNEXECUTED", "PASS", "FAIL", "BLOCKED", "N_A", name="test_case_status", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    release_status.create(bind, checkfirst=True)
    test_case_priority.create(bind, checkfirst=True)
    test_case_type.create(bind, checkfirst=True)
    test_case_status.create(bind, checkfirst=True)

    op.create_table(
        "releases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("cluster", sa.String(length=50), nullable=True),
        sa.Column("status", release_status, nullable=False, server_default="DRAFT"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "version", "platform", name="uq_release_name_version_platform"),
    )

    op.create_table(
        "test_cases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("release_id", sa.Integer(), nullable=False),
        sa.Column("test_case_id", sa.String(length=20), nullable=False),
        sa.Column("component", sa.String(length=150), nullable=False),
        sa.Column("test_case_name", sa.String(length=250), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("user_type", sa.String(length=100), nullable=True),
        sa.Column("priority", test_case_priority, nullable=False, server_default="CRITICAL"),
        sa.Column("test_type", test_case_type, nullable=False, server_default="FUNCTIONAL"),
        sa.Column("status", test_case_status, nullable=False, server_default="UNEXECUTED"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["release_id"], ["releases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "release_id", "test_case_id", name="uq_test_case_release_test_case_id"
        ),
    )
    op.create_index("idx_test_cases_release_id", "test_cases", ["release_id"])

    op.create_table(
        "test_steps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("test_case_id", sa.Integer(), nullable=False),
        sa.Column("step_number", sa.Integer(), nullable=False),
        sa.Column("test_step", sa.Text(), nullable=False),
        sa.Column("expected_result", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["test_case_id"], ["test_cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("test_case_id", "step_number", name="uq_test_step_case_step_number"),
    )
    op.create_index("idx_test_steps_test_case_id", "test_steps", ["test_case_id"])


def downgrade() -> None:
    op.drop_index("idx_test_steps_test_case_id", table_name="test_steps")
    op.drop_table("test_steps")
    op.drop_index("idx_test_cases_release_id", table_name="test_cases")
    op.drop_table("test_cases")
    op.drop_table("releases")

    bind = op.get_bind()
    test_case_status.drop(bind, checkfirst=True)
    test_case_type.drop(bind, checkfirst=True)
    test_case_priority.drop(bind, checkfirst=True)
    release_status.drop(bind, checkfirst=True)
