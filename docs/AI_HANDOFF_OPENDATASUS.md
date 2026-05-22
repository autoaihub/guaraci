# AI Handoff: OpenDataSUS and Agent Guidelines

This document is the single-source context handoff for future AI-agent conversations in the Guaraci repository.

## 1. Current State (`0.5.0`)

- Project: `Guaraci` `0.5.0`
- Official workflow: **Docker-first**
- Local Python without Docker: **WIP** and not officially supported
- Sources currently registered in the jobs/UI pipeline:
  - `snis`, `sinisa` (`gov.br` crawler)
  - `doses_aplicadas_pni`, `zikavirus` (`opendatasus api`)
  - generated OpenDataSUS DEMAS sources from `guaraci/opendatasus/utils/swagger.json`
  - `sinan`, `sim`, `sih` (`pysus ftp`)

## 2. Current OpenDataSUS Contract

### 2.1 `doses_aplicadas_pni`

- Base native API filters: `start_year`, `end_year`
- Optional local refinement: `start_date`, `end_date`, `uf`
- Technical or optional parameters: `batch_size`, `max_pages`, `resource_id`, `api_base_url`, `keep_raw`
- `keep_raw` default: `false`
- Optional export: `output_format` with `csv`, `parquet`, or `sqlite`
- Reliability behavior:
  - client errors should distinguish connectivity, timeout, HTTP, configuration, and response-format failures
  - datasource errors should add endpoint, page, package, or resource context when available
  - warnings such as truncation and export preservation should be visible in `export_warning` and manifest metadata

### 2.2 `zikavirus`

- Base native API filters: `start_year`, `end_year`
- Optional local refinement: `start_date`, `end_date`, `uf`
- Technical or optional parameters: `batch_size`, `max_pages`, `api_base_url`, `keep_raw`
- `keep_raw` default: `false`
- Optional export: `output_format` with `csv`, `parquet`, or `sqlite`

### 2.3 Generated DEMAS sources

- Source registry: `guaraci/services/opendatasus_registry.py`
- Generator: `scripts/scaffold_opendatasus.py`
- Source-specific native Swagger parameters are exposed in the schema as `basico`.
- Path parameters such as `codigo_cnes` are required and substituted into DEMAS endpoint paths.
- Query parameters are passed only when declared by the local Swagger catalog for the endpoint.
- `limit` and `offset` are controlled internally through `batch_size` and page iteration.
- Request manifests include `api_params` and per-endpoint query parameters for traceability.

## 3. Implementation Principles for AI Agents

1. Do not break existing sources.
2. Respect the current architecture:
   - `DownloadService` for registration, schema, and validation
   - `DownloadJobService` for queueing, status, progress, logs, retry, and cancellation
3. Every new source must:
   - define a `SourceDescriptor`
   - declare `SourceParameterSpec`
   - reject unknown parameters through the default validation path
4. Prefer native upstream API filters in the basic UX.
5. Keep technical parameters and local refinements in the advanced UI block; keep native API filters in the basic block.
6. Preserve consistent `JobResult` output and `/jobs/{job_id}/output` semantics.
7. Cover changes with service, API, job, and datasource tests.
8. Update documentation in the same change set.

## 4. Key Files for Evolution

- `guaraci/services/downloads.py`
- `guaraci/services/jobs.py`
- `guaraci/opendatasus/client.py`
- `guaraci/opendatasus/datasource.py`
- `guaraci/opendatasus/utils/swagger_catalog.py`
- `guaraci/api/main.py`
- `guaraci/api/static/index.html`

## 5. Quick Checklist for OpenDataSUS Changes

1. Update the source schema in `DownloadService`.
2. Guarantee parameter normalization for year, format, and booleans.
3. Implement or adjust the datasource collection flow for DEMAS or CKAN as required by the source.
4. Keep job progress and logs understandable in the queued-job flow.
5. Validate output artifacts such as `manifest`, `exported_files`, `export_warning`, and any raw output.
6. Cover the behavior with tests.
7. Update:
   - `README.md`
   - `docs/ARCHITECTURE.md`
   - `docs/API_REFERENCE.md`
   - `docs/UI_GUIDE.md`
   - `docs/SOURCES_AND_FILTERS.md`
   - `CHANGELOG.md` when applicable

## 6. Useful Validation Commands (Docker)

```bash
# Main suite
docker run --rm -v "$(pwd):/app" guaraci python -m pytest tests/ -v

# Focused OpenDataSUS, services, API, and jobs suite
docker run --rm -v "$(pwd):/app" guaraci python -m pytest \
  tests/test_opendatasus_client.py \
  tests/test_opendatasus_swagger_catalog.py \
  tests/test_opendatasus_generated_registry.py \
  tests/test_opendatasus_datasource.py \
  tests/test_services.py \
  tests/test_api.py \
  tests/test_jobs.py \
  tests/test_config.py -q

# Low-volume live smoke check against DEMAS.
# Use --samples for path-based endpoints when representative IDs are available.
docker run --rm -v "$(pwd):/app" guaraci python scripts/smoke_opendatasus_sources.py --allow-failures

# Run the local API inside the container
docker run --rm -it -p 8002:8000 -v "$(pwd):/app" guaraci \
  uvicorn guaraci.api.main:app --host 0.0.0.0 --port 8000 --no-access-log
```

## 7. Base Prompt for a New Maintenance Chat

Use the block below when starting a new maintenance conversation:

---
I want to evolve OpenDataSUS support in the Guaraci project while keeping compatibility with the current workflow.

Context:
- Current version: 0.5.0
- Official workflow: Docker-first
- Current OpenDataSUS sources: doses_aplicadas_pni, zikavirus
- Current OpenDataSUS contract:
  - base: start_year/end_year
  - optional refinement: start_date/end_date/uf
  - keep_raw defaults to false
  - optional export in csv/parquet/sqlite
- Architecture: DownloadService + DownloadJobService + dynamic UI schema
- Rules: reject unknown parameters, do not break current sources, update tests and docs

At the end:
- list changed files
- explain trade-offs
- provide exact Docker test commands
---


---
? [Índice da documentação](README.md) · [Voltar ao projeto](../README.md)
