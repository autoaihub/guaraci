# AGENTS: Diretrizes de Trabalho no Guaraci

Este arquivo define direcionamento tecnico para agentes de IA que atuam neste repositorio.

## 1) Contexto do projeto

- Versao atual: `0.4.1`
- Caminho suportado oficialmente: **Docker-first**
- Execucao Python local sem Docker: **WIP** (nao tratar como caminho principal)

## 2) Regras de arquitetura

1. Respeitar `DownloadService` + `DownloadJobService`.
2. Toda fonte deve ter:
   - `SourceDescriptor`,
   - schema declarativo com `SourceParameterSpec`,
   - validacao de parametros desconhecidos.
3. Retorno de execucao deve ser compativel com `JobResult`.
4. UI deve continuar dirigida por schema (`/sources/{source}/schema`).

## 3) Diretrizes de produto (filtros e UX)

1. Filtros basicos devem privilegiar parametros nativos da API/fonte.
2. Parametros tecnicos e refinamentos locais devem ir para `Filtragem avancada`.
3. `output_dir` deve permanecer no bloco basico, antes de `output_format`.
4. No launcher desktop, priorizar UX com pasta `Guaraci Downloads`.

## 4) OpenDataSUS (estado atual)

- Fontes: `doses_aplicadas_pni`, `zikavirus`
- Contrato atual:
  - base: `start_year`, `end_year`
  - refinamento opcional: `start_date`, `end_date`, `uf`
  - `keep_raw`: padrao `false`
  - exportacao opcional: `csv|parquet|sqlite`

Regra de nomenclatura:
- nao introduzir aliases para `source`; use apenas nomes canonicos no `DownloadService`.

## 5) Qualidade minima em cada mudanca

1. Nao quebrar fontes existentes.
2. Cobrir com testes (service, API, jobs, datasource quando aplicavel).
3. Atualizar documentacao no mesmo ciclo:
   - `README.md`
   - `docs/ARCHITECTURE.md`
   - `docs/API_REFERENCE.md`
   - `docs/UI_GUIDE.md`
   - `docs/SOURCES_AND_FILTERS.md`
   - `docs/AI_HANDOFF_OPENDATASUS.md`

## 6) Comandos de validacao (Docker)

```bash
docker run --rm -v "$(pwd):/app" guaraci python -m pytest tests/ -v
```

```bash
docker run --rm -v "$(pwd):/app" guaraci python -m pytest \
  tests/test_opendatasus_swagger_catalog.py \
  tests/test_opendatasus_datasource.py \
  tests/test_services.py \
  tests/test_api.py \
  tests/test_jobs.py \
  tests/test_config.py -q
```
