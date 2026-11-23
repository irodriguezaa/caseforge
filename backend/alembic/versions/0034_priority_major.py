"""Add MAJOR to test_case_priority.

Revision ID: 0034
Revises: 0033
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0034"
down_revision: Union[str, None] = "0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE test_case_priority ADD VALUE IF NOT EXISTS 'MAJOR'")


def downgrade() -> None:
    # PostgreSQL no elimina un valor de ENUM que ya puede estar en uso.
    pass
