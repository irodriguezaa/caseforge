"""Map application release types to NUEVO and REVALIDACION.

EVOLUTIVO without origin becomes NUEVO (first Release of an Entregable).
EVOLUTIVO with origin becomes REVALIDACION (later version).
The Postgres enum value EVOLUTIVO is left in place; the application no longer uses it.

Revision ID: 0024
Revises: 0023
Create Date: 2026-09-05
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE releases
        SET release_type = 'REVALIDACION'
        WHERE release_type = 'EVOLUTIVO' AND parent_release_id IS NOT NULL
        """
    )
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
