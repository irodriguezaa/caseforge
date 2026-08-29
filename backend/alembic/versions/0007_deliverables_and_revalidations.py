"""Add Deliverable, Release lineage (release_type/parent_release_id), and TestCaseRevalidation

Approved design ("Alternative C"): TestCase is NOT modified and NOT duplicated. Revalidation
executions are tracked in a new, independent test_case_revalidations table.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-28

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

release_type_enum = postgresql.ENUM("EVOLUTIVO", "REVALIDACION", name="release_type", create_type=False)
# Reuses the EXISTING test_case_status Postgres enum type (created back in 0001) -- never
# recreated here, only referenced, since TestCaseRevalidation shares that exact vocabulary.
test_case_status_enum = postgresql.ENUM(
    "UNEXECUTED", "PASS", "FAIL", "BLOCKED", "N_A", name="test_case_status", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()

    op.create_table(
        "deliverables",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_deliverables_name"),
    )

    release_type_enum.create(bind, checkfirst=True)
    op.add_column("releases", sa.Column("deliverable_id", sa.Integer(), nullable=True))
    op.add_column("releases", sa.Column("release_type", release_type_enum, nullable=True))
    op.add_column("releases", sa.Column("parent_release_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_releases_deliverable_id", "releases", "deliverables", ["deliverable_id"], ["id"], ondelete="SET NULL"
    )
    op.create_foreign_key(
        "fk_releases_parent_release_id", "releases", "releases", ["parent_release_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("idx_releases_deliverable_id", "releases", ["deliverable_id"])
    op.create_index("idx_releases_parent_release_id", "releases", ["parent_release_id"])

    op.create_table(
        "test_case_revalidations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("release_id", sa.Integer(), nullable=False),
        sa.Column("test_case_id", sa.Integer(), nullable=False),
        sa.Column("status", test_case_status_enum, nullable=False, server_default="UNEXECUTED"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["release_id"], ["releases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["test_case_id"], ["test_cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("release_id", "test_case_id", name="uq_revalidation_release_test_case"),
    )
    op.create_index("idx_revalidations_release_id", "test_case_revalidations", ["release_id"])
    op.create_index("idx_revalidations_test_case_id", "test_case_revalidations", ["test_case_id"])


def downgrade() -> None:
    op.drop_index("idx_revalidations_test_case_id", table_name="test_case_revalidations")
    op.drop_index("idx_revalidations_release_id", table_name="test_case_revalidations")
    op.drop_table("test_case_revalidations")

    op.drop_index("idx_releases_parent_release_id", table_name="releases")
    op.drop_index("idx_releases_deliverable_id", table_name="releases")
    op.drop_constraint("fk_releases_parent_release_id", "releases", type_="foreignkey")
    op.drop_constraint("fk_releases_deliverable_id", "releases", type_="foreignkey")
    op.drop_column("releases", "parent_release_id")
    op.drop_column("releases", "release_type")
    op.drop_column("releases", "deliverable_id")

    bind = op.get_bind()
    release_type_enum.drop(bind, checkfirst=True)

    op.drop_table("deliverables")
