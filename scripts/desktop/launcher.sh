#!/usr/bin/env bash
set -euo pipefail

IMAGE="${IMAGE:-guaraci}"
CONTAINER_NAME="${CONTAINER_NAME:-guaraci-desktop}"
HOST_PORT="${HOST_PORT:-8002}"
PROJECT_DIR="${PROJECT_DIR:-$(pwd)}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
START_SCRIPT="${SCRIPT_DIR}/start-guaraci.sh"
STATUS_SCRIPT="${SCRIPT_DIR}/status-guaraci.sh"
STOP_SCRIPT="${SCRIPT_DIR}/stop-guaraci.sh"

show_menu() {
  clear
  cat <<EOF
===============================
 Guaraci Desktop Launcher
===============================
Container: ${CONTAINER_NAME}
Porta    : ${HOST_PORT}
Projeto  : ${PROJECT_DIR}

1) Iniciar API/UI
2) Iniciar API/UI (rebuild)
3) Status
4) Abrir UI no navegador
5) Ver logs do container
6) Parar container
0) Sair
EOF
}

start_default() {
  IMAGE="${IMAGE}" CONTAINER_NAME="${CONTAINER_NAME}" HOST_PORT="${HOST_PORT}" PROJECT_DIR="${PROJECT_DIR}" "${START_SCRIPT}"
}

start_rebuild() {
  IMAGE="${IMAGE}" CONTAINER_NAME="${CONTAINER_NAME}" HOST_PORT="${HOST_PORT}" PROJECT_DIR="${PROJECT_DIR}" REBUILD=1 "${START_SCRIPT}"
}

show_status() {
  CONTAINER_NAME="${CONTAINER_NAME}" HOST_PORT="${HOST_PORT}" "${STATUS_SCRIPT}"
}

open_ui() {
  local url="http://localhost:${HOST_PORT}/"
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "${url}" >/dev/null 2>&1 || true
    echo "[guaraci] UI aberta em ${url}"
  elif command -v open >/dev/null 2>&1; then
    open "${url}" >/dev/null 2>&1 || true
    echo "[guaraci] UI aberta em ${url}"
  else
    echo "[guaraci] Abra manualmente: ${url}"
  fi
}

show_logs() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "[guaraci] Docker CLI não encontrado."
    return
  fi
  echo "[guaraci] CTRL+C para sair dos logs."
  docker logs -f "${CONTAINER_NAME}"
}

stop_container() {
  CONTAINER_NAME="${CONTAINER_NAME}" "${STOP_SCRIPT}"
}

pause_prompt() {
  read -r -p "Pressione ENTER para continuar..." _
}

while true; do
  show_menu
  read -r -p "Escolha uma opção: " choice
  case "${choice}" in
    1) start_default; pause_prompt ;;
    2) start_rebuild; pause_prompt ;;
    3) show_status; pause_prompt ;;
    4) open_ui; pause_prompt ;;
    5) show_logs; pause_prompt ;;
    6) stop_container; pause_prompt ;;
    0) break ;;
    *) echo "Opção inválida."; sleep 1 ;;
  esac
done
