#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-guaraci-desktop}"

if ! command -v docker >/dev/null 2>&1; then
  echo "[guaraci] Docker CLI não encontrado." >&2
  exit 1
fi

if ! docker ps -a --filter "name=^/${CONTAINER_NAME}$" --format "{{.ID}}" | grep -q .; then
  echo "[guaraci] Container '$CONTAINER_NAME' não existe."
  exit 0
fi

echo "[guaraci] Parando e removendo '$CONTAINER_NAME'..."
docker rm -f "$CONTAINER_NAME" >/dev/null
echo "[guaraci] Container removido."
