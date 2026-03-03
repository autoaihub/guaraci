# Guia de Instalacao

Este projeto deve ser considerado **Docker-first**.

## Status de suporte

- Suportado oficialmente: execucao via Docker (CLI, API e UI).
- Nao suportado oficialmente: execucao Python local sem Docker (WIP).

## Pre-requisitos

- Docker Desktop (Windows/macOS) ou Docker Engine (Linux).
- Git.

## Instalacao rapida

```bash
git clone https://github.com/autoaihub/guaraci.git
cd guaraci
docker build -t guaraci .
```

## Verificacao basica

```bash
# Versao
docker run --rm guaraci python -c "import guaraci; print(guaraci.__version__)"

# Teste de instalacao do pacote
docker run --rm guaraci python -m pytest tests/test_install.py -v
```

## Operacao recomendada (launcher desktop)

### Windows (PowerShell)

```powershell
.\scripts\desktop\start-guaraci.ps1
```

A UI abre em `http://localhost:8002/`.

Outros comandos:

```powershell
.\scripts\desktop\launcher.ps1
.\scripts\desktop\status-guaraci.ps1
.\scripts\desktop\stop-guaraci.ps1
```

Atalhos `.cmd` (duplo clique):
- `scripts\desktop\launcher.cmd`
- `scripts\desktop\start-guaraci.cmd`
- `scripts\desktop\status-guaraci.cmd`
- `scripts\desktop\stop-guaraci.cmd`

### Linux/macOS (bash)

```bash
./scripts/desktop/start-guaraci.sh
```

Outros comandos:

```bash
./scripts/desktop/launcher.sh
./scripts/desktop/status-guaraci.sh
./scripts/desktop/stop-guaraci.sh
```

## Operacao manual sem launcher

### Subir API em porta customizada

PowerShell:

```powershell
docker run --rm -it -p 8002:8000 -v "${PWD}:/app" guaraci \
  uvicorn guaraci.api.main:app --host 0.0.0.0 --port 8000 --no-access-log
```

Bash:

```bash
docker run --rm -it -p 8002:8000 -v "$(pwd):/app" guaraci \
  uvicorn guaraci.api.main:app --host 0.0.0.0 --port 8000 --no-access-log
```

## Testes no container

```bash
# suite completa
docker run --rm -v "$(pwd):/app" guaraci python -m pytest tests/ -v

# API/jobs
docker run --rm -v "$(pwd):/app" guaraci python -m pytest tests/test_api.py tests/test_jobs.py -v
```

## Estrategia de dados e volumes

Sempre monte o projeto em `/app` para persistir saidas no host:

- Windows PowerShell: `-v "${PWD}:/app"`
- Linux/macOS: `-v "$(pwd):/app"`

Sem volume mount, os dados ficam dentro do container efemero.

## Troubleshooting rapido

### Porta em uso

Erro comum: `Bind for 0.0.0.0:8002 failed: port is already allocated`

Acoes:
1. Trocar porta host (`-p 8003:8000`).
2. Parar container ativo (`scripts/desktop/stop-guaraci.*`).

### API de pe mas UI sem dados

Verifique:
- `GET /health`
- `GET /sources`
- permissao de escrita em `data/`

### Botao "Abrir Pasta" em Docker

Em container, abrir pasta no host nao e direto. Use o caminho mostrado em `host_output_dir` na UI/API.

## Execucao local sem Docker (WIP)

Este caminho existe apenas para desenvolvimento pontual e pode falhar.

Limites atuais:
- comportamento inconsistente entre sistemas,
- maior risco de conflito de dependencias (PySUS/FTP stack),
- nao e caminho validado para usuarios finais.

Se for necessario testar localmente, use por sua conta e valide em Docker antes de considerar resultado como definitivo.
