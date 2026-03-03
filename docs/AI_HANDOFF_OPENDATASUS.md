# AI Handoff: OpenDataSUS e Diretrizes para Agentes

Este documento serve como ponto unico de contexto para novas conversas com agentes de IA no projeto Guaraci.

## 1) Estado atual (0.4.1)

- Projeto: `Guaraci` `0.4.1`
- Modo oficial: **Docker-first**
- Python local sem Docker: **WIP** (nao suportado oficialmente)
- Fontes registradas no pipeline de jobs/UI:
  - `snis`, `sinisa` (crawler gov.br)
  - `doses_aplicadas_pni`, `zikavirus` (opendatasus api)
  - `sinan`, `sim`, `sih` (pysus ftp)

## 2) Contrato atual OpenDataSUS

### 2.1 `doses_aplicadas_pni`

- Filtros base (API nativa): `start_year`, `end_year`
- Refino local opcional: `start_date`, `end_date`, `uf`
- Tecnicos/opcionais: `batch_size`, `max_pages`, `resource_id`, `api_base_url`, `keep_raw`
- `keep_raw`: padrao `false`
- Exportacao opcional: `output_format` em `csv|parquet|sqlite`

### 2.2 `zikavirus`

- Filtros base (API nativa): `start_year`, `end_year`
- Refino local opcional: `start_date`, `end_date`, `uf`
- Tecnicos/opcionais: `batch_size`, `max_pages`, `api_base_url`, `keep_raw`
- `keep_raw`: padrao `false`
- Exportacao opcional: `output_format` em `csv|parquet|sqlite`

## 3) Principios de implementacao (agentes IA)

1. Nao quebrar fontes existentes.
2. Respeitar arquitetura atual:
   - `DownloadService` (registro/schema/validacao)
   - `DownloadJobService` (fila/status/progresso/log/retry/cancel)
3. Toda nova fonte deve:
   - ter `SourceDescriptor`,
   - declarar `SourceParameterSpec`,
   - rejeitar parametros desconhecidos (validacao padrao).
4. Preferir filtros basicos nativos da API de origem.
5. Filtros tecnicos e refinamentos locais devem ficar em bloco avancado na UI.
6. Manter retorno consistente em `JobResult` e no endpoint `/jobs/{job_id}/output`.
7. Cobrir mudancas com testes de service/API/jobs/datasource.
8. Atualizar documentacao no mesmo PR.

## 4) Arquivos-chave para evolucao

- `guaraci/services/downloads.py`
- `guaraci/services/jobs.py`
- `guaraci/opendatasus/client.py`
- `guaraci/opendatasus/datasource.py`
- `guaraci/opendatasus/utils/swagger_catalog.py`
- `guaraci/api/main.py`
- `guaraci/api/static/index.html`

## 5) Checklist rapido para mudancas OpenDataSUS

1. Ajustar schema da fonte no `DownloadService`.
2. Garantir normalizacao de params (ex.: ano, formato, bool).
3. Implementar/ajustar coleta no datasource (DEMAS/CKAN conforme fonte).
4. Garantir progresso/log compreensivel no fluxo de jobs.
5. Validar output (`manifest`, `exported_files`, `export_warning`, `raw_file`).
6. Cobrir com testes.
7. Atualizar:
   - `README.md`
   - `docs/ARCHITECTURE.md`
   - `docs/API_REFERENCE.md`
   - `docs/UI_GUIDE.md`
   - `docs/SOURCES_AND_FILTERS.md`
   - `CHANGELOG.md` (quando aplicavel)

## 6) Comandos uteis de validacao (Docker)

```bash
# Suite principal
docker run --rm -v "$(pwd):/app" guaraci python -m pytest tests/ -v

# Suite focada em servicos/api/jobs/opendatasus
docker run --rm -v "$(pwd):/app" guaraci python -m pytest \
  tests/test_opendatasus_swagger_catalog.py \
  tests/test_opendatasus_datasource.py \
  tests/test_services.py \
  tests/test_api.py \
  tests/test_jobs.py \
  tests/test_config.py -q

# Subir API local no container
docker run --rm -it -p 8002:8000 -v "$(pwd):/app" guaraci \
  uvicorn guaraci.api.main:app --host 0.0.0.0 --port 8000 --no-access-log
```

## 7) Prompt base para novo chat de manutencao

Use este bloco quando precisar iniciar um novo chat:

---
Quero evoluir OpenDataSUS no projeto Guaraci mantendo compatibilidade com o fluxo atual.

Contexto:
- Versao atual: 0.4.1
- Modo oficial: Docker-first
- Fontes OpenDataSUS atuais: doses_aplicadas_pni, zikavirus
- Contrato atual OpenDataSUS:
  - base: start_year/end_year
  - refinamento opcional: start_date/end_date/uf
  - keep_raw false por padrao
  - exportacao opcional csv/parquet/sqlite
- Arquitetura: DownloadService + DownloadJobService + schema dinamico na UI
- Regras: rejeitar parametros desconhecidos, nao quebrar fontes atuais, atualizar testes e docs.

Ao final:
- listar arquivos alterados,
- explicar trade-offs,
- informar comandos exatos de teste em Docker.
---
