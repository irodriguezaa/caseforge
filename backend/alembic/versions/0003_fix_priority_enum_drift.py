"""Correct test_case_priority drift: ensure it is exactly BLOCKER/CRITICAL

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-28

Context: during Sprint 2 development, migration 0001 was edited in place to narrow
TestCasePriority from {LOW, MEDIUM, HIGH, CRITICAL} down to {BLOCKER, CRITICAL} before it had
ever been applied against a real database, in the belief that no environment had run it yet.
That assumption was wrong for at least one environment: Alembic had already recorded "0001" as
applied there, so re-running `alembic upgrade head` after the edit never re-executed 0001's
`CREATE TYPE test_case_priority ...` -- the live enum kept whatever value set was current when
0001 first ran. This left that database's enum out of sync with the application code, causing
`invalid input value for enum test_case_priority: "BLOCKER"` on insert.

This migration is idempotent and safe regardless of which of the two possible historical value
sets is present (the only two that ever existed in this codebase's history):
  - Already correct: {BLOCKER, CRITICAL} -- values pass through unchanged.
  - Stale/original: {LOW, MEDIUM, HIGH, CRITICAL} -- mapped to the new 2-value scale below.

Mapping for stale values (best-effort; this data is Sprint 2 development/validation data, not
production QC records): HIGH -> BLOCKER (most severe old bucket maps to the most severe new
one), CRITICAL -> CRITICAL (unchanged), MEDIUM -> CRITICAL, LOW -> CRITICAL. Any other
unrecognized value also falls back to CRITICAL rather than failing the migration.

Editing already-applied migrations is not safe practice; going forward, schema corrections like
this belong in new migrations, never in edits to 0001/0002.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_VALUE_MAP_SQL = """
    CASE priority_column::text
        WHEN 'BLOCKER' THEN 'BLOCKER'
        WHEN 'CRITICAL' THEN 'CRITICAL'
        WHEN 'HIGH' THEN 'BLOCKER'
        WHEN 'MEDIUM' THEN 'CRITICAL'
        WHEN 'LOW' THEN 'CRITICAL'
        ELSE 'CRITICAL'
    END
"""


def upgrade() -> None:
    # New type under a temporary name, guaranteed to hold exactly the correct two values,
    # regardless of what the existing `test_case_priority` type currently contains.
    op.execute("CREATE TYPE test_case_priority_fixed AS ENUM ('BLOCKER', 'CRITICAL')")

    op.execute(
        "ALTER TABLE test_cases ALTER COLUMN priority DROP DEFAULT"
    )
    op.execute(
        "ALTER TABLE test_cases ALTER COLUMN priority TYPE test_case_priority_fixed "
        "USING (" + _VALUE_MAP_SQL.replace("priority_column", "priority") + ")::test_case_priority_fixed"
    )
    op.execute(
        "ALTER TABLE test_cases ALTER COLUMN priority SET DEFAULT 'CRITICAL'"
    )

    op.execute(
        "ALTER TABLE defects ALTER COLUMN severity TYPE test_case_priority_fixed "
        "USING (" + _VALUE_MAP_SQL.replace("priority_column", "severity") + ")::test_case_priority_fixed"
    )

    op.execute("DROP TYPE test_case_priority")
    op.execute("ALTER TYPE test_case_priority_fixed RENAME TO test_case_priority")


def downgrade() -> None:
    # Not reversible: the source value sets (LOW/MEDIUM/HIGH) are not recoverable once
    # collapsed into BLOCKER/CRITICAL. Downgrading past this point requires a manual decision
    # about what a 4-value scale should mean again, so this is intentionally left as a no-op.
    pass
