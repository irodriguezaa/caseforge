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

nginx_conf_readable() {
  local uid gid
  uid="$(docker exec "$PROXY" id -u)"
  gid="$(docker exec "$PROXY" id -g)"
  docker exec -u root "$PROXY" chmod 644 "$NGINX_CONF"
  docker exec -u root "$PROXY" chown "${uid}:${gid}" "$NGINX_CONF"
}

extract_proxy_conf() {
  local dest="$1" image wd src cid
  image="$(docker inspect -f '{{.Config.Image}}' "$PROXY")"
  wd="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' "$PROXY")"
  echo "proxy image=$image"
  echo "compose dir=$wd"
  src=""
  if [[ -n "$wd" && -d "$wd" ]]; then
    src="$(find "$wd" -name 'default.conf' -size +0c 2>/dev/null | head -1 || true)"
  fi
  if [[ -n "$src" ]]; then
    echo "origen: $src"
    cat "$src" > "$dest"
  else
    echo "origen: imagen (docker create, sin recreate Django)"
    cid="$(docker create "$image")"
    docker cp "$cid:$NGINX_CONF" "$dest"
    docker rm -f "$cid" >/dev/null
  fi
}

write_nginx_pid() {
  local nginx_uid nginx_gid
  nginx_uid="$(docker exec "$PROXY" id -u)"
  nginx_gid="$(docker exec "$PROXY" id -g)"
  docker exec -u root "$PROXY" sh -c "
    master=\$(ps | grep '[n]ginx: master' | awk '{print \$1; exit}')
    [ -n \"\$master\" ] || master=1
    printf '%s\n' \"\$master\" > /tmp/nginx.pid
    chown ${nginx_uid}:${nginx_gid} /tmp/nginx.pid
    chmod 644 /tmp/nginx.pid
  "
}

# Recupera default.conf desde el compose host o la imagen. No recreate Django.
restore_nginx() {
  if ! docker inspect "$PROXY" >/dev/null 2>&1; then
    die "No está $PROXY. No se toca Django si el proxy no existe."
  fi
  local tmp
  tmp="$(mktemp)"
  extract_proxy_conf "$tmp"
  if [[ ! -s "$tmp" ]]; then
    rm -f "$tmp"
    die "No hay default.conf en el host ni en la imagen. No se tocó Django."
  fi
  wc -c "$tmp"
  docker exec -u root -i "$PROXY" sh -c "cat > '$NGINX_CONF'" < "$tmp"
  rm -f "$tmp"
  nginx_conf_readable
  docker restart "$PROXY"
  nginx_conf_readable
  echo "default.conf restaurado. Django compose no se recreó."
}

ensure_qcpulse_locations() {
  if docker exec -u root "$PROXY" grep -q 'qcpulse-frontend-1:3000' "$NGINX_CONF"; then
    return 0
  fi
  local conf_tmp has_map
  conf_tmp="$(mktemp)"
  docker exec -u root "$PROXY" cat "$NGINX_CONF" > "$conf_tmp"
  has_map=0
  if docker exec -u root "$PROXY" grep -q 'map \$http_upgrade \$connection_upgrade' /etc/nginx/nginx.conf "$NGINX_CONF" 2>/dev/null; then
    has_map=1
  fi
  python3 - "$conf_tmp" "$has_map" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
has_map = sys.argv[2] == "1"
text = path.read_text()
if "qcpulse-frontend-1:3000" in text:
    raise SystemExit(0)
block = """
    location = /qcpulse {
        client_max_body_size 25m;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_pass http://qcpulse-frontend-1:3000;
    }
    location ^~ /qcpulse/ {
        client_max_body_size 25m;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_pass http://qcpulse-frontend-1:3000;
    }
"""
idx = text.rfind("}")
if idx < 0:
    raise SystemExit("nginx default.conf sin bloque server")
text = text[:idx] + block + text[idx:]
if not has_map and "map $http_upgrade $connection_upgrade" not in text:
    text = (
        "map $http_upgrade $connection_upgrade {\n"
        "    default upgrade;\n"
        "    ''      close;\n"
        "}\n\n"
        + text
    )
path.write_text(text)
PY
  docker exec -u root -i "$PROXY" sh -c "cat > '$NGINX_CONF'" < "$conf_tmp"
  rm -f "$conf_tmp"
  nginx_conf_readable
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
  if ! docker exec -u root "$PROXY" sh -c "test -s '$NGINX_CONF'"; then
    echo "default.conf vacío; restaurando desde imagen/compose."
    restore_nginx
  fi
  nginx_conf_readable
  ensure_qcpulse_locations
  docker exec -u root "$PROXY" sed -i \
    's|http://caseforge-frontend-1:3000|http://qcpulse-frontend-1:3000|g' \
    "$NGINX_CONF"
  docker exec -u root "$PROXY" sed -i \
    's/proxy_set_header Connection "upgrade";/proxy_set_header Connection $connection_upgrade;/' \
    "$NGINX_CONF"
  if ! docker exec -u root "$PROXY" grep -q 'client_max_body_size 25m' "$NGINX_CONF"; then
    docker exec -u root "$PROXY" sed -i \
      '/location = \/qcpulse {/a\        client_max_body_size 25m;' \
      "$NGINX_CONF"
    docker exec -u root "$PROXY" sed -i \
      '/location \^~ \/qcpulse\/ {/a\        client_max_body_size 25m;' \
      "$NGINX_CONF"
  fi
  docker exec -u root "$PROXY" sed -i \
    's/proxy_read_timeout 300s/proxy_read_timeout 600s/;s/proxy_send_timeout 300s/proxy_send_timeout 600s/' \
    "$NGINX_CONF"
  if ! docker exec -u root "$PROXY" grep -q 'proxy_read_timeout 600s' "$NGINX_CONF"; then
    docker exec -u root "$PROXY" sed -i \
      '/location = \/qcpulse {/a\        proxy_read_timeout 600s;' \
      "$NGINX_CONF"
    docker exec -u root "$PROXY" sed -i \
      '/location = \/qcpulse {/a\        proxy_send_timeout 600s;' \
      "$NGINX_CONF"
    docker exec -u root "$PROXY" sed -i \
      '/location \^~ \/qcpulse\/ {/a\        proxy_read_timeout 600s;' \
      "$NGINX_CONF"
    docker exec -u root "$PROXY" sed -i \
      '/location \^~ \/qcpulse\/ {/a\        proxy_send_timeout 600s;' \
      "$NGINX_CONF"
  fi
  nginx_conf_readable
  write_nginx_pid
  docker exec "$PROXY" nginx -t
  docker exec "$PROXY" nginx -s reload || docker restart "$PROXY"
  nginx_conf_readable
  echo "nginx: /qcpulse/ → $FRONTEND. Django no se recreó."
}

diagnose() {
  echo "==== git ===="
  git log -1 --oneline
  echo "==== red frontend ===="
  docker inspect "$FRONTEND" --format '{{json .NetworkSettings.Networks}}' 2>/dev/null || echo "no $FRONTEND"
  echo "==== proxy ps/logs ===="
  docker ps -a --filter "name=$PROXY" --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
  docker logs --tail 20 "$PROXY" 2>&1 || true
  echo "==== nginx qcpulse ===="
  docker exec -u root "$PROXY" ls -la "$NGINX_CONF" /tmp/nginx.pid 2>&1 || true
  docker exec "$PROXY" nginx -t 2>&1 || true
  docker inspect "$PROXY" --format 'RestartCount={{.RestartCount}} Image={{.Config.Image}} WD={{index .Config.Labels "com.docker.compose.project.working_dir"}}' 2>/dev/null || true
  echo "==== $NGINX_CONF ===="
  docker exec -u root "$PROXY" cat "$NGINX_CONF" 2>&1 || true
  echo "==== curl host 3001 ===="
  curl -sS -o /dev/null -w 'GET 3001/qcpulse/ -> %{http_code}\n' --max-time 10 http://127.0.0.1:3001/qcpulse/ || echo "3001 FAIL"
  echo "==== curl via :80 ===="
  curl -sS -o /dev/null -w 'GET :80/qcpulse/ -> %{http_code}\n' --max-time 10 http://127.0.0.1/qcpulse/ || echo ":80 FAIL"
  echo "==== POST via :80 (401/403/409 ok; 000 = nginx/Next colgado) ===="
  curl -sS -o /dev/null -w 'POST :80 -> %{http_code}\n' --max-time 10 \
    -X POST http://127.0.0.1/qcpulse/api/releases/1 \
    -H 'Content-Type: application/json' \
    -d '{"status":"IN_PROGRESS"}' || echo "POST :80 FAIL"
  echo "==== POST via 3001 ===="
  curl -sS -o /dev/null -w 'POST 3001 -> %{http_code}\n' --max-time 10 \
    -X POST http://127.0.0.1:3001/qcpulse/api/releases/1 \
    -H 'Content-Type: application/json' \
    -d '{"status":"IN_PROGRESS"}' || echo "POST 3001 FAIL"
}

usage() {
  cat <<'EOF'
Uso: ./scripts/qc4.sh <comando>

  up          Build + arranque QCPulse, une la red y corrige nginx /qcpulse/
  fix-nginx     Reconecta el frontend y sed de /qcpulse (sin recreate Django)
  restore-nginx Restaura default.conf desde compose/imagen y reinicia solo el proxy
  diagnose      SHA, nginx, curls GET/PATCH (solo lectura)
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
  restore-nginx)
    restore_nginx
    reconnect_frontend
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
