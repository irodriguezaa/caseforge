"""Generation metadata and QC estimation on persisted Test Cases.

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-01

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("test_cases", sa.Column("test_data", sa.Text(), nullable=True))
    op.add_column(
        "test_cases",
        sa.Column("requires_condition", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column("test_cases", sa.Column("evidence", sa.Text(), nullable=True))
    op.add_column("test_cases", sa.Column("justification", sa.Text(), nullable=True))
    op.add_column("test_cases", sa.Column("technical_epic", sa.String(length=250), nullable=True))
    op.add_column("test_cases", sa.Column("technical_story", sa.String(length=500), nullable=True))
    op.add_column("test_cases", sa.Column("scenario_origin", sa.Text(), nullable=True))
    op.add_column("test_cases", sa.Column("related_rn", sa.String(length=250), nullable=True))
    op.add_column("test_cases", sa.Column("confidence", sa.String(length=16), nullable=True))
    op.add_column("test_cases", sa.Column("complexity", sa.String(length=16), nullable=True))
    op.add_column("test_cases", sa.Column("estimation_hours", sa.Numeric(6, 2), nullable=True))
    op.add_column(
        "test_cases",
        sa.Column("generated_by_engine", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("test_cases", "generated_by_engine")
    op.drop_column("test_cases", "estimation_hours")
    op.drop_column("test_cases", "complexity")
    op.drop_column("test_cases", "confidence")
    op.drop_column("test_cases", "related_rn")
    op.drop_column("test_cases", "scenario_origin")
    op.drop_column("test_cases", "technical_story")
    op.drop_column("test_cases", "technical_epic")
    op.drop_column("test_cases", "justification")
    op.drop_column("test_cases", "evidence")
    op.drop_column("test_cases", "requires_condition")
    op.drop_column("test_cases", "test_data")
