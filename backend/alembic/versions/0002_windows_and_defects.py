"""Add operational_windows, release_windows, defects, and TestCase window links

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-27

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

window_status = postgresql.ENUM("PLANNED", "ACTIVE", "CLOSED", name="window_status", create_type=False)
defect_status = postgresql.ENUM("OPEN", "CLOSED", name="defect_status", create_type=False)
# Reuses the existing test_case_priority enum type created in 0001 -- not re-created here.
test_case_priority = postgresql.ENUM(
    "BLOCKER", "CRITICAL", name="test_case_priority", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    window_status.create(bind, checkfirst=True)
    defect_status.create(bind, checkfirst=True)

    op.create_table(
        "operational_windows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("cluster", sa.String(length=50), nullable=True),
        sa.Column("status", window_status, nullable=False, server_default="PLANNED"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "release_windows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("release_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", window_status, nullable=False, server_default="PLANNED"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["release_id"], ["releases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_release_windows_release_id", "release_windows", ["release_id"])

    op.create_table(
        "defects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("test_case_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=250), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("severity", test_case_priority, nullable=False),
        sa.Column("status", defect_status, nullable=False, server_default="OPEN"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["test_case_id"], ["test_cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_defects_test_case_id", "defects", ["test_case_id"])

    op.add_column("test_cases", sa.Column("operational_window_id", sa.Integer(), nullable=True))
    op.add_column("test_cases", sa.Column("release_window_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_test_cases_operational_window_id",
        "test_cases",
        "operational_windows",
        ["operational_window_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_test_cases_release_window_id",
        "test_cases",
        "release_windows",
        ["release_window_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_test_cases_operational_window_id", "test_cases", ["operational_window_id"])
    op.create_index("idx_test_cases_release_window_id", "test_cases", ["release_window_id"])


def downgrade() -> None:
    op.drop_index("idx_test_cases_release_window_id", table_name="test_cases")
    op.drop_index("idx_test_cases_operational_window_id", table_name="test_cases")
    op.drop_constraint("fk_test_cases_release_window_id", "test_cases", type_="foreignkey")
    op.drop_constraint("fk_test_cases_operational_window_id", "test_cases", type_="foreignkey")
    op.drop_column("test_cases", "release_window_id")
    op.drop_column("test_cases", "operational_window_id")

    op.drop_index("idx_defects_test_case_id", table_name="defects")
    op.drop_table("defects")

    op.drop_index("idx_release_windows_release_id", table_name="release_windows")
    op.drop_table("release_windows")

    op.drop_table("operational_windows")

    bind = op.get_bind()
    defect_status.drop(bind, checkfirst=True)
    window_status.drop(bind, checkfirst=True)
