#!/usr/bin/env bash
# QcPulse v2 — atajos de Docker (correr desde la raíz del proyecto).
#   ./scripts/qcv2.sh build                                   reconstruye la imagen del backend con la v2
#   ./scripts/qcv2.sh run WEB WEBCL-2060 WEBCL-1586          genera casos (sin base de datos) → exports/qcv2/
#   ./scripts/qcv2.sh bench exports/benchmark/Luminia.xlsx exports/qcv2/qcv2_WEB_x.xlsx [--judge]
#   ./scripts/qcv2.sh test                                    pruebas de la v2
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p exports/qcv2 exports/benchmark

case "${1:-}" in
  build)
    docker compose build backend
    ;;
  run)
    shift
    [ $# -ge 2 ] || { echo "Uso: $0 run <DISPOSITIVO> <EPICA> [EPICA...]"; exit 1; }
    device="$1"; shift
    docker compose run --rm --no-deps -v "$PWD/exports/qcv2:/out" backend \
      python -m app.services.qc_v2.cli "$@" --device "$device" --out /out
    ;;
  bench)
    shift
    [ $# -ge 2 ] || { echo "Uso: $0 bench exports/<luminia>.xlsx exports/<qcpulse>.xlsx [--judge]"; exit 1; }
    luminia="$1"; qcpulse="$2"; shift 2
    case "$luminia$qcpulse" in exports/*exports/*) ;; *) echo "Ambos archivos deben estar dentro de exports/"; exit 1;; esac
    docker compose run --rm --no-deps -v "$PWD/exports:/exports" backend \
      python -m app.services.qc_v2.benchmark --luminia "/$luminia" --qcpulse "/$qcpulse" --out /exports/benchmark "$@"
    ;;
  test)
    docker compose --profile test build backend-test
    docker compose --profile test run --rm backend-test python -m pytest tests/test_qc_v2.py -q
    ;;
  *)
    sed -n 2,6p "$0"
    exit 1
    ;;
esac
