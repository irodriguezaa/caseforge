#!/usr/bin/env bash
# QcPulse v2-B — atajos de Docker (correr desde la raíz del proyecto).
#   ./scripts/qcv2b.sh build
#   ./scripts/qcv2b.sh run WEB WEBCL-1586
#   ./scripts/qcv2b.sh test
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p exports/qcv2b

case "${1:-}" in
  build)
    docker compose build backend
    ;;
  run)
    shift
    [ $# -ge 2 ] || { echo "Uso: $0 run <DISPOSITIVO> <EPICA> [EPICA...]"; exit 1; }
    device="$1"; shift
    docker compose run --rm --no-deps -v "$PWD/exports/qcv2b:/out" backend \
      python -m app.services.qc_v2b.cli "$@" --device "$device" --out /out
    ;;
  test)
    docker compose --profile test build backend-test
    docker compose --profile test run --rm backend-test python -m pytest tests/test_qc_v2b.py tests/test_qc_v2.py -q
    ;;
  *)
    sed -n 2,6p "$0"
    exit 1
    ;;
esac
