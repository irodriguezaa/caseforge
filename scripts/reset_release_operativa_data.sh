#!/usr/bin/env bash
# Reset Release Apps, Operativas and Release BE business rows.
# Keeps schema, Alembic version and qc_tickets (KPIs).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! docker compose ps postgres --status running >/dev/null 2>&1; then
  echo "PostgreSQL no está arriba. Arranca con: docker compose up -d postgres" >&2
  exit 1
fi

docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' <<'SQL'
BEGIN;
TRUNCATE TABLE
  defects,
  test_steps,
  test_case_revalidations,
  test_cases,
  release_windows,
  release_analyses,
  epcs,
  releases,
  be_releases,
  operativa_releases
RESTART IDENTITY CASCADE;
COMMIT;

SELECT 'releases' AS t, COUNT(*) FROM releases
UNION ALL SELECT 'operativa_releases', COUNT(*) FROM operativa_releases
UNION ALL SELECT 'be_releases', COUNT(*) FROM be_releases
UNION ALL SELECT 'epcs', COUNT(*) FROM epcs
UNION ALL SELECT 'test_cases', COUNT(*) FROM test_cases
UNION ALL SELECT 'qc_tickets', COUNT(*) FROM qc_tickets;
SQL

echo "Listo. Releases, Operativas y BE en cero. qc_tickets se conservó."
