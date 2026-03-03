# Guaraci

Plataforma para download e orquestracao de fontes publicas brasileiras, com foco atual em:
- `SNIS` e `SINISA` (crawler gov.br)
- `SINAN`, `SIM` e `SIH` (PySUS/FTP DATASUS)
- `OpenDataSUS` (API, fontes `doses_aplicadas_pni` e `zikavirus`)

Versao atual: `0.4.1`

## Estado atual do projeto

- Fluxo **oficial e suportado**: **Docker-first** (CLI, API e UI web).
- Fluxo sem Docker (Python local puro): **WIP / nao suportado oficialmente no momento**.
  - Pode funcionar em alguns ambientes.
  - Nao e considerado caminho estavel, especialmente no Windows.

## O que ja funciona hoje

- Download assincrono via API com fila de jobs, cancelamento e retry.
- UI web desktop para usuarios tecnicos e nao tecnicos.
- Schema dinamico por fonte (`/sources/{source}/schema`) para montar filtros na UI.
- Progresso de jobs com:
  - percentual,
  - arquivo atual,
  - bytes transferidos,
  - ETA,
  - logs estruturados.
- Persistencia de jobs em disco (`data/jobs/download_jobs.json`).
- Exportacao opcional de datasets processados (`csv`, `parquet`, `sqlite`) para fontes PySUS e OpenDataSUS.

## Arquitetura (resumo)

- `guaraci/services/downloads.py`
  - Registro de fontes.
  - Validacao de parametros por schema.
  - Adaptadores para `gov.br crawl` e `pysus ftp`.
- `guaraci/services/jobs.py`
  - Execucao em background.
  - Estados de job (`queued`, `running`, `completed`, `failed`, `canceled`).
  - Retry/cancel.
  - Persistencia e logs.
- `guaraci/api/main.py`
  - Endpoints HTTP (health, schema, jobs, logs, output).
- `guaraci/api/static/index.html`
  - UI web desktop.
  - Formulario dinamico por schema.
  - Monitoramento de jobs e pasta de saida.

Detalhes completos:
- `docs/README.md`
- `docs/ARCHITECTURE.md`
- `docs/API_REFERENCE.md`
- `docs/UI_GUIDE.md`
- `docs/SOURCES_AND_FILTERS.md`
- `docs/AI_HANDOFF_OPENDATASUS.md`
- `AGENTS.md`

## Quick Start (Docker-first)

### 1) Build

```bash
docker build -t guaraci .
```

### 2) Subir API + UI (launcher)

PowerShell (Windows):

```powershell
.\scripts\desktop\start-guaraci.ps1
```

Bash (Linux/macOS):

```bash
./scripts/desktop/start-guaraci.sh
```

Padrao: UI em `http://localhost:8002/`.

No launcher desktop, os downloads sao centralizados em `Guaraci Downloads` na Area de Trabalho.

### 3) Verificar saude da API

```bash
curl http://localhost:8002/health
```

Resposta esperada:

```json
{"status":"ok","version":"0.4.1"}
```

## Uso via UI (resumo)

1. Escolher fonte.
2. Preencher filtros (campos sao gerados pelo schema da fonte).
3. Confirmar revisao e criar job.
4. Acompanhar progresso e logs no painel.
5. Copiar caminho de saida ou abrir pasta.

Observacoes importantes:
- Em Docker, abrir pasta direto do container pode nao funcionar no host.
- A UI mostra `host_output_dir` quando disponivel para abrir no sistema host.
- Mensagem de UX na tela: consulte os arquivos na pasta `Guaraci Downloads` da Area de Trabalho.

Guia detalhado: `docs/UI_GUIDE.md`.

## Uso via API (resumo)

Base URL (launcher): `http://localhost:8002`

- `GET /health`
- `GET /sources`
- `GET /sources/{source}/schema`
- `POST /jobs`
- `GET /jobs`
- `GET /jobs/{job_id}`
- `POST /jobs/{job_id}/cancel`
- `POST /jobs/{job_id}/retry`
- `GET /jobs/{job_id}/logs`
- `GET /jobs/{job_id}/output`
- `POST /jobs/{job_id}/open-output`

Referencia completa: `docs/API_REFERENCE.md`.

## Uso via CLI (Docker)

Entrypoints principais:
- `python -m guaraci.cli.main`
- `python -m guaraci.cli.snis_cli`
- `python -m guaraci.cli.sinan_cli`
- `python -m guaraci.cli.sim_cli`
- `python -m guaraci.cli.sih_cli`

Exemplos:

```bash
# Ajuda geral
docker run --rm -it -v "$(pwd):/app" guaraci python -m guaraci.cli.main --help

# SNIS (gov.br)
docker run --rm -it -v "$(pwd):/app" guaraci \
  python -m guaraci.cli.snis_cli download \
  --file-kinds planilhas --modules agua --extract-archives

# SINAN
docker run --rm -it -v "$(pwd):/app" guaraci \
  python -m guaraci.cli.sinan_cli download 2023 2024 --diseases RAIV --format csv

# SIM
docker run --rm -it -v "$(pwd):/app" guaraci \
  python -m guaraci.cli.sim_cli download 2023 2024 --groups CID10 --states SP RJ --format csv

# SIH
docker run --rm -it -v "$(pwd):/app" guaraci \
  python -m guaraci.cli.sih_cli download 2024 2025 --groups RJ --states RJ --months 1 --format csv
```

Observacao:
- No fluxo de **jobs/UI**, `SIH` nao expoe filtro `ano`.
- Na CLI direta de `sih_cli`, o parametro `--ano` ainda existe para filtro de exportacao local.

## Fontes e filtros

Tabela detalhada por fonte: `docs/SOURCES_AND_FILTERS.md`.

Resumo rapido:
- `snis` / `sinisa`:
  - `results_url`, `file_kinds`, `modules`, `extract_archives`, `overwrite`, `timeout`.
- `doses_aplicadas_pni` (modo `opendatasus api`):
  - coleta base (API nativa): `start_year`, `end_year`
  - refinamento opcional: `uf`, `start_date`, `end_date`
  - exportacao: `output_format`
  - avancado: `keep_raw` (padrao `false`), `batch_size`, `max_pages`, `resource_id`, `api_base_url`
- `zikavirus` (modo `opendatasus api`):
  - coleta base (API nativa): `start_year`, `end_year`
  - refinamento opcional: `start_date`, `end_date`, `uf`
  - exportacao: `output_format`
  - avancado: `keep_raw` (padrao `false`), `batch_size`, `max_pages`, `api_base_url`
- `sinan`:
  - coleta: `start_year`, `end_year`, `diseases`
  - exportacao: `output_format`, `uf`, `municipio`, `sexo`, `faixa_etaria`, `evolucao`, `classificacao`
- `sim`:
  - coleta: `start_year`, `end_year`, `groups`, `states`
  - exportacao: `output_format`, `uf`, `municipio`, `sexo`, `causa_basica`, `ano_obito`
- `sih`:
  - coleta: `start_year`, `end_year`, `groups`, `states`, `months`
  - exportacao: `output_format`, `uf`, `municipio`, `sexo`, `mes`

Observacao de nomenclatura OpenDataSUS:
- use nomes explicitos de fonte: `doses_aplicadas_pni` ou `zikavirus`.

## Estrutura de saida de dados

### SNIS/SINISA (crawler)

```text
<output_dir>/
  raw/
  extracted/            # quando extract_archives=true
  manifest.json
```

### PySUS (SINAN/SIM/SIH)

```text
<output_dir>/
  raw/                  # artefatos materializados
  <arquivos_exportados> # quando output_format definido
  manifest.json         # quando houve materializacao de artefatos
```

### OpenDataSUS

```text
<output_dir>/
  manifest.json
  <arquivos_exportados> # quando output_format definido
  raw/                  # apenas quando keep_raw=true
```

No endpoint `/jobs/{job_id}/output`, alem do output path, a API retorna:
- `output_format`
- `exported_files`
- `export_warning` (quando formato foi pedido mas nada foi exportado)

## Launcher desktop

Scripts disponiveis:
- Windows (PowerShell + `.cmd`): `scripts/desktop/`
- Linux/macOS (bash): `scripts/desktop/`

Comandos uteis (Windows):

```powershell
.\scripts\desktop\launcher.ps1
.\scripts\desktop\start-guaraci.ps1
.\scripts\desktop\status-guaraci.ps1
.\scripts\desktop\stop-guaraci.ps1
```

Comandos uteis (Linux/macOS):

```bash
./scripts/desktop/launcher.sh
./scripts/desktop/start-guaraci.sh
./scripts/desktop/status-guaraci.sh
./scripts/desktop/stop-guaraci.sh
```

## Desenvolvimento e testes

```bash
# Testes
docker run --rm -v "$(pwd):/app" guaraci python -m pytest tests/ -v

# Testes focados
docker run --rm -v "$(pwd):/app" guaraci python -m pytest tests/test_api.py tests/test_jobs.py -v
```

## Limitacoes atuais

- Execucao Python local fora de Docker: **WIP**.
- Abertura de pasta via UI em ambiente Docker depende do host path mapping.
- Algumas fontes PySUS podem falhar por instabilidades externas de FTP/rede.

## Versao e roadmap imediato

- Release atual: `0.4.1` (MVP OpenDataSUS integrado ao fluxo de jobs/UI).
- Proximo alvo: expandir datasets OpenDataSUS e endurecer retries/observabilidade por fonte.

## Documentacao complementar

- `INSTALL.md`: instalacao e operacao suportada.
- `DOCKER_WORKFLOW.md`: rotina operacional Docker.
- `CONTRIBUTING.md`: fluxo para contribuicao.
- `IMPROVEMENTS.md`: historico e direcao de evolucao.
- `CHANGELOG.md`: historico de versoes.
