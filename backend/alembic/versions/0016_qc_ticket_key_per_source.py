"""Allow the same Jira issue in detection and leak filters independently.

The reference dashboard_qco.html keeps #112929 and #113062 as two lists. A unique
issue_key made leak refresh overwrite QC_DETECTED rows and inflate/deflate totals.

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-31

"""

from typing import Sequence, Union

from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_qc_ticket_issue_key", "qc_tickets", type_="unique")
    op.create_unique_constraint(
        "uq_qc_ticket_issue_key_view_source",
        "qc_tickets",
        ["issue_key", "view", "source"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_qc_ticket_issue_key_view_source", "qc_tickets", type_="unique")
    op.create_unique_constraint("uq_qc_ticket_issue_key", "qc_tickets", ["issue_key"])
