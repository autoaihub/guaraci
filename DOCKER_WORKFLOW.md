# Docker Workflow

Guia operacional detalhado do fluxo Docker do Guaraci.

## 1) Build da imagem

```bash
docker build -t guaraci .
```

Quando usar `--no-cache`:
- upgrade de dependencias,
- comportamento inconsistente apos varias mudancas,
- suspeita de cache quebrado.

```bash
docker build --no-cache -t guaraci .
```

## 2) Modos de execucao

### 2.1 Launcher desktop (recomendado)

Windows (PowerShell):

```powershell
.\scripts\desktop\start-guaraci.ps1
```

Linux/macOS (bash):

```bash
./scripts/desktop/start-guaraci.sh
```

Padrao:
- container: `guaraci-desktop`
- porta host: `8002`
- API interna: `8000`

### 2.2 Execucao manual

```bash
docker run --rm -it -p 8002:8000 -v "$(pwd):/app" guaraci \
  uvicorn guaraci.api.main:app --host 0.0.0.0 --port 8000 --no-access-log
```

## 3) Launcher: comportamento interno

`start-guaraci` executa:
1. valida Docker ativo,
2. opcionalmente faz rebuild,
3. remove container antigo com mesmo nome,
4. sobe API com mapeamento de volume e porta,
5. injeta variaveis para mapear path do container para path do host:
   - `GUARACI_HOST_APP_ROOT`
   - `GUARACI_CONTAINER_APP_ROOT`
6. espera `GET /health` retornar `{"status":"ok"}`.

## 4) Comandos operacionais

Windows:

```powershell
.\scripts\desktop\launcher.ps1
.\scripts\desktop\status-guaraci.ps1
.\scripts\desktop\stop-guaraci.ps1
```

Linux/macOS:

```bash
./scripts/desktop/launcher.sh
./scripts/desktop/status-guaraci.sh
./scripts/desktop/stop-guaraci.sh
```

## 5) Fluxo de dados com volume mount

Sempre monte `project:/app`:

- dados gerados em `/app/data` no container ficam no `./data` do host,
- arquivos de job persistem em `data/jobs/download_jobs.json`.

Sem mount, dados sao perdidos ao remover container.

## 6) API/UI no Docker

URLs usuais:
- UI: `http://localhost:8002/`
- Health: `http://localhost:8002/health`

Checagens uteis:

```bash
curl http://localhost:8002/health
curl http://localhost:8002/sources
curl http://localhost:8002/sources/sih/schema
```

## 7) Jobs assincronos

### Ciclo

1. `POST /jobs`
2. monitoramento: `GET /jobs` e `GET /jobs/{job_id}`
3. logs: `GET /jobs/{job_id}/logs`
4. saida: `GET /jobs/{job_id}/output`

### Status de job

- `queued`
- `running`
- `cancel_requested`
- `completed`
- `failed`
- `canceled`

### Retry

Permitido para:
- `failed`
- `canceled`

Bloqueado para:
- `completed`
- `running`
- `queued`

## 8) Progresso e logs

A UI mostra:
- percentual,
- ETA,
- arquivo atual,
- bytes transferidos,
- logs estruturados.

No backend, eventos sao persistidos com timestamp compacto `YYYY-MM-DD HH:MM:SS`.

## 9) Output e abertura de pasta

Endpoint:
- `GET /jobs/{job_id}/output`

Retorna, entre outros:
- `output_dir`
- `host_output_dir` (quando mapeavel)
- `exported_files`
- `output_format`
- `export_warning`

Endpoint:
- `POST /jobs/{job_id}/open-output`

Com Docker, normalmente retorna aviso para abrir manualmente no host usando `host_output_dir`.

## 10) Troubleshooting

### Porta ja alocada

Erro tipico:
- `Bind for 0.0.0.0:8002 failed: port is already allocated`

Acoes:
1. mudar porta host,
2. parar container anterior,
3. validar com `docker ps`.

### Jobs antigos com erro de restart

Se a API reiniciar no meio da execucao, jobs em andamento podem ser marcados como interrompidos/failed.

### Muito log HTTP no console

Suba uvicorn com `--no-access-log` (launcher ja usa por padrao).

### Exportacao solicitada sem arquivo gerado

Verificar em `/jobs/{job_id}/output`:
- `exported_files` vazio,
- `export_warning` presente.

Isso indica que download pode ter funcionado, mas exportacao filtrada nao gerou dataset final.

## 11) Desenvolvimento no Docker

```bash
# testes
docker run --rm -v "$(pwd):/app" guaraci python -m pytest tests/ -v

# shell interativo
docker run --rm -it -v "$(pwd):/app" guaraci bash
```

## 12) Nota sobre Python local sem Docker

Fluxo local sem Docker esta em WIP e nao e o caminho recomendado para operacao.
Use Docker para validacao final de comportamento.
