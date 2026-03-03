#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-guaraci-desktop}"
HOST_PORT="${HOST_PORT:-8002}"

if ! command -v docker >/dev/null 2>&1; then
  echo "[guaraci] Docker CLI não encontrado." >&2
  exit 1
fi

ROW="$(docker ps -a --filter "name=^/${CONTAINER_NAME}$" --format "{{.Names}}|{{.Status}}|{{.Ports}}")"
if [[ -z "$ROW" ]]; then
  echo "[guaraci] Nenhum container encontrado com nome '$CONTAINER_NAME'."
  exit 0
fi

IFS='|' read -r NAME STATUS PORTS <<<"$ROW"
echo "Container : ${NAME}"
echo "Status    : ${STATUS}"
echo "Ports     : ${PORTS}"

HEALTH_URL="http://localhost:${HOST_PORT}/health"
if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
  echo "Health    : ok (${HEALTH_URL})"
else
  echo "Health    : indisponível (${HEALTH_URL})"
fi
