#!/usr/bin/env bash
# Instala ou atualiza o Guaraci hospedado na conta atual, sem sudo e sem Docker.
#   bash deploy/hospedado/instalar.sh            # instala ou atualiza
#   bash deploy/hospedado/instalar.sh --servico  # e registra a unidade do systemd
# Pressupõe o repositório já em $GUARACI_APP_DIR (padrão ~/guaraci).
set -euo pipefail

APP_DIR="${GUARACI_APP_DIR:-$HOME/guaraci}"
ENV_FILE="${GUARACI_ENV_FILE:-$HOME/guaraci.env}"
cd "$APP_DIR"

echo "1/4 Ambiente Python"
if [ ! -x .venv/bin/python ]; then
  if ! python3 -m venv .venv 2>/dev/null; then
    # O Debian separa o venv em outro pacote (python3-venv). Sem sudo, o uv
    # cria o ambiente sozinho e fica em ~/.local/bin.
    rm -rf .venv
    if ! command -v uv >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/uv" ]; then
      curl -LsSf https://astral.sh/uv/install.sh | sh
    fi
    UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
    "$UV" venv --python python3 .venv
    "$UV" pip install --python .venv/bin/python pip
  fi
fi

echo "2/4 Dependências"
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -e ".[datasus,api,trabalho]"

echo "3/4 Configuração"
if [ ! -f "$ENV_FILE" ]; then
  cp deploy/hospedado/guaraci.env.example "$ENV_FILE"
  SECRET="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))')"
  sed -i "s|^GUARACI_SECRET_KEY=.*|GUARACI_SECRET_KEY=$SECRET|" "$ENV_FILE"
  sed -i "s|/home/sabia|$HOME|g" "$ENV_FILE"
  echo "   Criado $ENV_FILE com segredo novo. Revise GUARACI_PROXY_IP e GUARACI_CONTACT."
fi
chmod 600 "$ENV_FILE"
chmod +x deploy/hospedado/iniciar.sh

echo "4/4 Conferência"
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a
.venv/bin/python -c "import guaraci.api.main as m; assert m.HOSTED and m.runtime is not None; m.runtime.stop(); print('   API carrega no modo hospedado.')"

if [ "${1:-}" = "--servico" ]; then
  mkdir -p "$HOME/.config/systemd/user"
  cp deploy/hospedado/guaraci.service "$HOME/.config/systemd/user/guaraci.service"
  systemctl --user daemon-reload
  systemctl --user enable guaraci
  systemctl --user restart guaraci
  echo "   Serviço do usuário ativo: systemctl --user status guaraci"
fi

echo
echo "Pronto. Primeiro administrador (uma vez só):"
echo "  set -a; . $ENV_FILE; set +a; .venv/bin/guaraci admin create --email <seu e-mail>"
