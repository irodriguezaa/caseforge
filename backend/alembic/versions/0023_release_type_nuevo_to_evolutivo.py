"""Map legacy NUEVO release_type rows to EVOLUTIVO.

The Postgres enum value NUEVO is kept so existing DBs remain readable; the application
no longer creates NUEVO.

Revision ID: 0023
Revises: 0022
Create Date: 2026-09-05
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE releases
        SET release_type = 'EVOLUTIVO'
        WHERE release_type = 'NUEVO'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE releases
        SET release_type = 'NUEVO'
        WHERE release_type = 'EVOLUTIVO' AND parent_release_id IS NULL
        """
    )
