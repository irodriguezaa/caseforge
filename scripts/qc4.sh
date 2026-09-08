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
PROXY="django-nginx-docker-deployment_proxy_1"
NGINX_CONF="/etc/nginx/conf.d/default.conf"

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

fix_nginx() {
  if ! docker inspect "$PROXY" >/dev/null 2>&1; then
    die "No está $PROXY. No se toca Django si el proxy no existe."
  fi
  reconnect_frontend
  docker exec "$PROXY" sed -i \
    's|http://caseforge-frontend-1:3000|http://qcpulse-frontend-1:3000|g' \
    "$NGINX_CONF"
  docker exec "$PROXY" sed -i \
    's/proxy_set_header Connection "upgrade";/proxy_set_header Connection $connection_upgrade;/' \
    "$NGINX_CONF"
  if ! docker exec "$PROXY" grep -q 'client_max_body_size 25m' "$NGINX_CONF"; then
    docker exec "$PROXY" sed -i \
      '/location = \/qcpulse {/a\        client_max_body_size 25m;' \
      "$NGINX_CONF"
    docker exec "$PROXY" sed -i \
      '/location \^~ \/qcpulse\/ {/a\        client_max_body_size 25m;' \
      "$NGINX_CONF"
  fi
  docker exec "$PROXY" nginx -t
  docker exec "$PROXY" nginx -s reload
  echo "nginx: /qcpulse/ → $FRONTEND, Connection \$connection_upgrade, reload OK. Django no se recreó."
}

diagnose() {
  echo "==== git ===="
  git log -1 --oneline
  echo "==== red frontend ===="
  docker inspect "$FRONTEND" --format '{{json .NetworkSettings.Networks}}' 2>/dev/null || echo "no $FRONTEND"
  echo "==== nginx qcpulse ===="
  docker exec "$PROXY" grep -n -E 'qcpulse|Connection|proxy_pass|client_max_body' "$NGINX_CONF" || true
  echo "==== curl host 3001 ===="
  curl -sS -o /dev/null -w 'GET 3001/qcpulse/ -> %{http_code}\n' --max-time 10 http://127.0.0.1:3001/qcpulse/ || echo "3001 FAIL"
  echo "==== curl via :80 ===="
  curl -sS -o /dev/null -w 'GET :80/qcpulse/ -> %{http_code}\n' --max-time 10 http://127.0.0.1/qcpulse/ || echo ":80 FAIL"
  echo "==== PATCH via :80 (401/403/409 ok; 000 = nginx roto) ===="
  curl -sS -o /dev/null -w 'PATCH :80 -> %{http_code}\n' --max-time 10 \
    -X PATCH http://127.0.0.1/qcpulse/api/releases/1 \
    -H 'Content-Type: application/json' \
    -d '{"status":"IN_PROGRESS"}' || echo "PATCH :80 FAIL"
  echo "==== PATCH via 3001 ===="
  curl -sS -o /dev/null -w 'PATCH 3001 -> %{http_code}\n' --max-time 10 \
    -X PATCH http://127.0.0.1:3001/qcpulse/api/releases/1 \
    -H 'Content-Type: application/json' \
    -d '{"status":"IN_PROGRESS"}' || echo "PATCH 3001 FAIL"
}

usage() {
  cat <<'EOF'
Uso: ./scripts/qc4.sh <comando>

  up          Build + arranque QCPulse, une la red y corrige nginx /qcpulse/
  fix-nginx   Reconecta el frontend y arregla Connection/proxy_pass (sin recreate Django)
  diagnose    SHA, nginx, curls GET/PATCH (solo lectura)
  stop        Para frontend y backend (Postgres QCPulse sigue arriba)
  start       Arranca frontend y backend y reconecta la red
  restart     Reinicia frontend y backend y reconecta la red
  down        Para todo QCPulse (no borra volúmenes; Django no se toca)
  logs        Logs (opcional: frontend | backend | postgres)
  status      Contenedores QCPulse y Django (solo lectura)
  reconnect   Vuelve a unir qcpulse-frontend-1 a la red del proxy Django

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
    fix_nginx
    dc ps
    ;;
  fix-nginx)
    fix_nginx
    ;;
  diagnose)
    diagnose
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
