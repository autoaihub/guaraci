# Project Improvements

This document records the implemented progress so far and the next technical focus areas.

## 1. Consolidated Progress

### 1.1 Source layer

- `snis` and `sinisa` through the `gov.br` crawler flow with manifests
- `sinan`, `sim`, and `sih` through PySUS/FTP
- OpenDataSUS with canonical sources:
  - `doses_aplicadas_pni`
  - `zikavirus`
- OpenDataSUS DEMAS sources generated from the local Swagger catalog
- legacy BigQuery SNIS flow isolated in `guaraci/snis/legacy/`

### 1.2 Service layer

- source registry with declarative per-parameter schema
- strong parameter validation with unknown-field rejection
- separation between collection parameters and post-processing parameters for PySUS
- OpenDataSUS contract oriented around native filters:
  - base: `start_year`, `end_year`
  - optional local refinement: `start_date`, `end_date`, `uf`
  - `keep_raw` defaulting to `false`
- OpenDataSUS reliability diagnostics improved with:
  - categorized client failures for connectivity, timeout, HTTP, configuration, and response format
  - actionable hints attached to upstream failures
  - datasource context for package lookup, endpoint, page, and resource offset when a request fails
- removal of OpenDataSUS source aliases to reduce ambiguity
- materialization of PySUS artifacts in local `raw/` folders
- optional export in `csv`, `parquet`, and `sqlite` for PySUS and OpenDataSUS sources

### 1.3 Asynchronous jobs

- queued jobs with background execution
- status tracking, cancellation, and retry
- JSON persistence for job history
- progress reporting with percentage, bytes, current file, and ETA
- structured event logs

### 1.4 API and UI

- FastAPI endpoints for schema, jobs, logs, and output
- web UI with dynamic per-source forms
- separation between basic filters and the `Advanced Filtering` block
- `output_dir` kept in the basic block before `output_format`
- monitoring and output details in the dashboard
- display of `exported_files` and `export_warning`
- OpenDataSUS manifests now persist warning messages for troubleshooting and reprocessing guidance
- generated OpenDataSUS sources now pass declared Swagger query parameters, enforce path parameters, and record API parameters in manifests

## 2. Current Attention Points

1. Local execution without Docker
   Status: WIP.
   Risk: dependency and environment inconsistencies.
2. UX across heterogeneous sources
   Crawler and PySUS sources have different semantics.
   OpenDataSUS adds variation between native filters, generated Swagger filters, and local refinements.
   The product still needs clearer language and filter grouping for non-technical users.
3. External reliability
   FTP and web sources can fluctuate.
   The project still needs stronger observability and reprocessing strategies.

## 3. Recommended Direction

### 3.1 Short term

- refine UI UX by source type, especially crawler versus API or FTP flows
- improve user-oriented error messages
- expand test coverage for export and network failure scenarios
- increase regression coverage for progress and log behavior in API-based sources

### 3.2 Medium term

- a pluggable source catalog with richer per-field metadata
- better classification of filters by phase:
  - collection
  - transformation
  - export
- expanded OpenDataSUS integration for new datasets while keeping native basic filters per source and preserving generated-source traceability
- manifest standardization across all sources

### 3.3 Long term

- desktop distribution strategy for non-technical end users
- simpler installation flows focused on assisted operation
- eventual local non-Docker support once stability is proven

## 4. Definition of Ready for New Sources

A new source should ship with:

- declarative parameter schema
- strong input validation
- standardized `JobResult` output
- preference for native basic source filters instead of opaque aliases
- minimum test coverage
- updated documentation in:
  - `README.md`
  - `CHANGELOG.md`
  - `AGENTS.md`
  - `docs/ARCHITECTURE.md`
  - `docs/SOURCES_AND_FILTERS.md`
  - `docs/API_REFERENCE.md`
  - `docs/UI_GUIDE.md` when UX is impacted
  - `docs/AI_HANDOFF_OPENDATASUS.md`

## 5. Support Note

The current functional baseline is **Docker-first**.
Any path outside that flow should be treated as experimental until formal validation exists.
