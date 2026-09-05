"""OperativaRelease header (Paso 2) and configuration (Paso 3) fields.

Adds entregable/cluster plus QC configuration (dates, Jira filter, instrucciones).
Makes name nullable so an unreadable RN header is stored as empty rather than the
PDF filename. No QC-resource columns -- Operativas does not track those.

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-31

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("operativa_releases", sa.Column("entregable", sa.String(length=200), nullable=True))
    op.add_column("operativa_releases", sa.Column("cluster", sa.String(length=50), nullable=True))
    op.add_column("operativa_releases", sa.Column("start_date", sa.Date(), nullable=True))
    op.add_column("operativa_releases", sa.Column("end_date", sa.Date(), nullable=True))
    op.add_column("operativa_releases", sa.Column("jira_filter_url", sa.Text(), nullable=True))
    op.add_column("operativa_releases", sa.Column("jira_filter_manual", sa.Text(), nullable=True))
    op.add_column(
        "operativa_releases", sa.Column("instrucciones_adicionales", sa.Text(), nullable=True)
    )
    op.alter_column(
        "operativa_releases",
        "name",
        existing_type=sa.String(length=200),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "operativa_releases",
        "name",
        existing_type=sa.String(length=200),
        nullable=False,
    )
    op.drop_column("operativa_releases", "instrucciones_adicionales")
    op.drop_column("operativa_releases", "jira_filter_manual")
    op.drop_column("operativa_releases", "jira_filter_url")
    op.drop_column("operativa_releases", "end_date")
    op.drop_column("operativa_releases", "start_date")
    op.drop_column("operativa_releases", "cluster")
    op.drop_column("operativa_releases", "entregable")
