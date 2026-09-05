"""Add NUEVO to release_type. Existing EVOLUTIVO rows without origin become NUEVO.

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-04
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE release_type ADD VALUE IF NOT EXISTS 'NUEVO'")
    op.execute(
        """
        UPDATE releases
        SET release_type = 'NUEVO'
        WHERE release_type = 'EVOLUTIVO' AND parent_release_id IS NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE releases
        SET release_type = 'EVOLUTIVO'
        WHERE release_type = 'NUEVO'
        """
    )
