#!/usr/bin/env bash
# Sobe o Guaraci hospedado em primeiro plano (o systemd ou o cron cuidam de
# manter no ar). Um processo só: a fila de coletas vive na memória dele.
set -euo pipefail

APP_DIR="${GUARACI_APP_DIR:-$HOME/guaraci}"
ENV_FILE="${GUARACI_ENV_FILE:-$HOME/guaraci.env}"

if [ ! -f "$ENV_FILE" ]; then
  echo "Falta $ENV_FILE (veja deploy/hospedado/guaraci.env.example)." >&2
  exit 1
fi
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

if [ -z "${GUARACI_PROXY_IP:-}" ]; then
  echo "Aviso: GUARACI_PROXY_IP vazio; X-Forwarded-For será ignorado." >&2
  FORWARDED="127.0.0.1"
else
  FORWARDED="$GUARACI_PROXY_IP"
fi

mkdir -p "$(dirname "$GUARACI_DB_PATH")" "$GUARACI_OUTPUT_ROOT" "${GUARACI_DATA_ROOT:-$APP_DIR/data}"
cd "$APP_DIR"
exec "$APP_DIR/.venv/bin/python" -m uvicorn guaraci.api.main:app \
  --host "${GUARACI_HOST:-0.0.0.0}" \
  --port "${GUARACI_PORT:-8080}" \
  --workers 1 \
  --proxy-headers \
  --forwarded-allow-ips "$FORWARDED" \
  --no-server-header \
  --timeout-keep-alive 5 \
  --limit-concurrency 200
