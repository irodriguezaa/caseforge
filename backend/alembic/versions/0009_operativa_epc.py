"""Add OperativaRelease and Epc for the RN Operativo -> EPC -> test cases pipeline

Pasos 1-4 only (Cargar RN / EPCs detectados-filtro / Alcance funcional manual / Dispositivos
aplicables). Casos, estimación, recursos, cronograma, Excel/Zephyr, and real Jira integration
for children/acceptance-criteria are NOT part of this migration -- see Epc.alcance_funcional's
docstring for why that field is a plain manual text column for now.

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-30

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "operativa_releases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("pdf_filename", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "epcs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("operativa_release_id", sa.Integer(), nullable=False),
        sa.Column("brf_key", sa.String(length=30), nullable=False),
        sa.Column("epc_key", sa.String(length=30), nullable=True),
        sa.Column("titulo", sa.Text(), nullable=False),
        sa.Column("alcance", sa.String(length=50), nullable=True),
        sa.Column("nota_rte", sa.Text(), nullable=True),
        sa.Column("estado_jira", sa.String(length=50), nullable=True),
        sa.Column(
            "qc_suggestion",
            sa.Enum("SUGERIDO_INCLUIR", "SUGERIDO_EXCLUIR", "REQUIERE_REVISION", name="qc_suggestion"),
            nullable=False,
        ),
        sa.Column("include_in_qc", sa.Boolean(), nullable=False),
        sa.Column("alcance_funcional", sa.Text(), nullable=True),
        sa.Column("dispositivos_aplicables", sa.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["operativa_release_id"], ["operativa_releases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_epcs_operativa_release_id", "epcs", ["operativa_release_id"])


def downgrade() -> None:
    op.drop_index("idx_epcs_operativa_release_id", table_name="epcs")
    op.drop_table("epcs")
    sa.Enum(name="qc_suggestion").drop(op.get_bind(), checkfirst=True)
    op.drop_table("operativa_releases")
