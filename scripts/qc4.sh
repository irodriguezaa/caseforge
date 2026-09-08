#!/usr/bin/env bash
# QC-4 only: start/stop QCPulse. Never touches Django compose, volumes, or prune.
#
#   cd ~/qcpulse && ./scripts/qc4.sh up
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE_FILE="docker-compose.qc4.yml"
ENV_FILE=".env"
DJANGO_NET="django-nginx-docker-deployment_qc_network"
FRONTEND="qcpulse-frontend-1"

dc() {
  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"
}

die() {
  echo "$*" >&2
  exit 1
}

need_stack_files() {
  [[ -f "$COMPOSE_FILE" ]] || die "No está $COMPOSE_FILE. Ejecuta esto desde el clone ~/qcpulse."
  [[ -f "$ENV_FILE" ]] || die "No está $ENV_FILE. Cópialo de .env.example y no uses el .env del Mac."
}

reconnect_frontend() {
  if ! docker inspect "$FRONTEND" >/dev/null 2>&1; then
    echo "Aún no existe $FRONTEND; nada que conectar."
    return 0
  fi
  local err
  if err="$(docker network connect "$DJANGO_NET" "$FRONTEND" 2>&1)"; then
    echo "Red: $FRONTEND unido a $DJANGO_NET"
    return 0
  fi
  if echo "$err" | grep -qiE 'already (exists|attached)|already connected'; then
    echo "Red: $FRONTEND ya estaba en $DJANGO_NET"
    return 0
  fi
  echo "$err" >&2
  return 1
}

usage() {
  cat <<'EOF'
Uso: ./scripts/qc4.sh <comando>

  up         Build y arranque del stack QCPulse, luego une el frontend a la red de nginx
  stop       Para frontend y backend (Postgres QCPulse sigue arriba)
  start      Arranca frontend y backend y reconecta la red
  restart    Reinicia frontend y backend y reconecta la red
  down       Para todo QCPulse (no borra volúmenes; Django no se toca)
  logs       Logs (opcional: frontend | backend | postgres)
  status     Contenedores QCPulse y Django (solo lectura)
  reconnect  Vuelve a unir qcpulse-frontend-1 a la red del proxy Django

No usa docker-compose.yml, no hace prune, no hace down -v.
EOF
}

cmd="${1:-}"
shift || true

case "$cmd" in
  -h|--help|help|"")
    usage
    exit 0
    ;;
esac

need_stack_files

case "$cmd" in
  up)
    dc up -d --build
    reconnect_frontend
    dc ps
    ;;
  stop)
    dc stop frontend backend
    ;;
  start)
    dc start frontend backend
    reconnect_frontend
    ;;
  restart)
    dc restart frontend backend
    reconnect_frontend
    ;;
  down)
    dc down
    echo "QCPulse abajo. Volúmenes intactos. Django no se tocó."
    ;;
  logs)
    if [[ -n "${1:-}" ]]; then
      dc logs -f --tail 100 "$1"
    else
      dc logs -f --tail 100
    fi
    ;;
  status)
    echo "==== QCPulse ===="
    dc ps
    echo "==== servidor (Django debe seguir Up) ===="
    docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
    ;;
  reconnect)
    reconnect_frontend
    ;;
  *)
    usage >&2
    die "Comando desconocido: $cmd"
    ;;
esac
