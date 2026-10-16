"""BE QC scope labels and touched modules.

Revision ID: 0032
Revises: 0031
Create Date: 2026-10-15

Maps COMPLETO/SMOKE/ACOTADO to App validation labels and stores the module picker.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: Union[str, None] = "0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("be_releases") as batch:
        batch.alter_column(
            "regresivo_scope",
            existing_type=sa.String(length=20),
            type_=sa.String(length=80),
            existing_nullable=True,
        )
        batch.add_column(sa.Column("qc_matrix_touched_modules", sa.JSON(), nullable=True))
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE be_releases
            SET regresivo_scope = CASE regresivo_scope
                WHEN 'COMPLETO' THEN 'Regresión completa'
                WHEN 'SMOKE' THEN 'Smoke Test'
                WHEN 'ACOTADO' THEN 'Pruebas Acotadas'
                ELSE regresivo_scope
            END
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE be_releases
            SET regresivo_scope = CASE regresivo_scope
                WHEN 'Regresión completa' THEN 'COMPLETO'
                WHEN 'Smoke Test' THEN 'SMOKE'
                WHEN 'Pruebas Acotadas' THEN 'ACOTADO'
                WHEN 'N/A' THEN NULL
                ELSE regresivo_scope
            END
            """
        )
    )
    with op.batch_alter_table("be_releases") as batch:
        batch.drop_column("qc_matrix_touched_modules")
        batch.alter_column(
            "regresivo_scope",
            existing_type=sa.String(length=80),
            type_=sa.String(length=20),
            existing_nullable=True,
        )
