#!/usr/bin/env bash
set -euo pipefail

IMAGE="${IMAGE:-guaraci}"
CONTAINER_NAME="${CONTAINER_NAME:-guaraci-desktop}"
HOST_PORT="${HOST_PORT:-8002}"
# A API não tem autenticação: por padrão publica apenas em loopback.
# Para expor na rede local, defina BIND_ADDRESS=0.0.0.0 explicitamente.
BIND_ADDRESS="${BIND_ADDRESS:-127.0.0.1}"
PROJECT_DIR="${PROJECT_DIR:-$(pwd)}"
HOST_DESKTOP_DIR="${HOST_DESKTOP_DIR:-$HOME/Desktop}"
HOST_DOWNLOADS_DIR="${HOST_DOWNLOADS_DIR:-${HOST_DESKTOP_DIR}/Guaraci Downloads}"
REBUILD="${REBUILD:-0}"
ACCESS_LOG="${ACCESS_LOG:-0}"

if ! command -v docker >/dev/null 2>&1; then
  echo "[guaraci] Docker CLI não encontrado." >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "[guaraci] Docker não está ativo." >&2
  exit 1
fi

if [[ "$REBUILD" == "1" ]] || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "[guaraci] Build da imagem '$IMAGE'..."
  docker build -t "$IMAGE" "$PROJECT_DIR"
fi

if [[ ! -d "$HOST_DESKTOP_DIR" ]]; then
  HOST_DESKTOP_DIR="$PROJECT_DIR"
  HOST_DOWNLOADS_DIR="${HOST_DESKTOP_DIR}/Guaraci Downloads"
fi
mkdir -p "$HOST_DOWNLOADS_DIR"

EXISTING="$(docker ps -a --filter "name=^/${CONTAINER_NAME}$" --format "{{.ID}}|{{.Status}}")"
if [[ -n "$EXISTING" ]]; then
  STATUS="${EXISTING#*|}"
  if [[ "$STATUS" == Up* ]]; then
    echo "[guaraci] Container '$CONTAINER_NAME' já está ativo."
  else
    echo "[guaraci] Removendo container anterior '$CONTAINER_NAME'..."
    docker rm -f "$CONTAINER_NAME" >/dev/null
  fi
fi

if ! docker ps --filter "name=^/${CONTAINER_NAME}$" --format "{{.ID}}" | grep -q .; then
  echo "[guaraci] Iniciando API em http://localhost:${HOST_PORT} ..."
  UVICORN_ARGS=(uvicorn guaraci.api.main:app --host 0.0.0.0 --port 8000)
  if [[ "$ACCESS_LOG" != "1" ]]; then
    UVICORN_ARGS+=(--no-access-log)
  fi
  docker run -d \
    --name "$CONTAINER_NAME" \
    -p "${BIND_ADDRESS}:${HOST_PORT}:8000" \
    -v "${PROJECT_DIR}:/app" \
    -v "${HOST_DOWNLOADS_DIR}:/downloads" \
    -e "GUARACI_HOST_APP_ROOT=${PROJECT_DIR}" \
    -e "GUARACI_CONTAINER_APP_ROOT=/app" \
    -e "GUARACI_HOST_DOWNLOADS_ROOT=${HOST_DOWNLOADS_DIR}" \
    -e "GUARACI_CONTAINER_DOWNLOADS_ROOT=/downloads" \
    -e "GUARACI_DEFAULT_DOWNLOAD_ROOT=/downloads" \
    -e "GUARACI_DEFAULT_OUTPUT_ROOT=/downloads" \
    -e "GUARACI_OUTPUT_ROOT=/downloads" \
    "$IMAGE" \
    "${UVICORN_ARGS[@]}" >/dev/null
fi

HEALTH_URL="http://localhost:${HOST_PORT}/health"
for _ in $(seq 1 45); do
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    echo "[guaraci] API pronta em http://localhost:${HOST_PORT}/"
    echo "[guaraci] Consulte seus downloads em: ${HOST_DOWNLOADS_DIR}"
    echo "[guaraci] Para parar: ./scripts/desktop/stop-guaraci.sh"
    exit 0
  fi
  sleep 0.5
done

echo "[guaraci] API não respondeu em ${HEALTH_URL}." >&2
exit 1
