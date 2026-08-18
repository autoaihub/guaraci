#!/usr/bin/env bash
# Diagnóstico independente do Guaraci: confere se o Docker está pronto ANTES de
# rodar "docker build" ou "docker run". Rode isto primeiro se algo falhar — assim
# dá para saber se o problema é o Docker ou o Guaraci.
#
# Uso:  ./scripts/desktop/check-docker.sh
# Sai com código 0 se tudo estiver OK, 1 caso contrário.
set -uo pipefail

GREEN="\033[0;32m"; RED="\033[0;31m"; GRAY="\033[0;90m"; RESET="\033[0m"

status() {
  local ok=$1 label=$2 detail=${3:-}
  if [[ "$ok" == "1" ]]; then
    printf "${GREEN}[OK]${RESET}    %s\n" "$label"
  else
    printf "${RED}[FALHA]${RESET} %s\n" "$label"
  fi
  if [[ -n "$detail" ]]; then
    printf "${GRAY}        %s${RESET}\n" "$detail"
  fi
}

all_ok=1

if command -v docker >/dev/null 2>&1; then
  status 1 "Docker CLI instalado"
else
  status 0 "Docker CLI instalado" "Baixe o Docker Desktop: https://www.docker.com/products/docker-desktop/"
  all_ok=0
fi

if [[ "$all_ok" == "1" ]]; then
  if docker info >/dev/null 2>&1; then
    status 1 "Docker rodando (engine responde)"
  else
    status 0 "Docker rodando (engine responde)" "Abra o Docker Desktop e espere o icone da baleia parar de 'Starting...'. No Windows/WSL, se travar: 'wsl --shutdown' e abra o Docker Desktop de novo."
    all_ok=0
  fi
fi

if [[ "$all_ok" == "1" ]]; then
  if docker run --rm hello-world >/dev/null 2>&1; then
    status 1 "Consegue executar containers (teste hello-world)"
  else
    status 0 "Consegue executar containers (teste hello-world)" "O engine respondeu mas falhou ao rodar um container. Reinicie o Docker Desktop; se persistir, resete para configuracoes de fabrica."
    all_ok=0
  fi
fi

echo ""
if [[ "$all_ok" == "1" ]]; then
  printf "${GREEN}Docker esta pronto. Pode seguir com 'docker build -t guaraci .'${RESET}\n"
  exit 0
else
  printf "${RED}Docker NAO esta pronto - resolva os itens [FALHA] acima antes de continuar.${RESET}\n"
  printf "${RED}Se o Guaraci der erro depois disso, o problema ja nao e mais o Docker.${RESET}\n"
  exit 1
fi
