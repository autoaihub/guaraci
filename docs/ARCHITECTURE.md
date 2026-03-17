# Internal Architecture

## 1. Overview

Guaraci uses a layered architecture:

1. `datasources`
   Implement data source-specific download and read logic.
   Examples: `SnisDataSource`, `SinisaDataSource`, `SinanDataSource`, `SimDataSource`, `SihDataSource`, and `OpenDataSUSDataSource`.
2. `services/downloads`
   Registers supported sources, declares source parameter schemas, validates and normalizes input, and adapts source results to `JobResult`.
3. `services/jobs`
   Manages asynchronous jobs, status and progress tracking, disk persistence, and structured per-event logs.
4. `api/main`
   Exposes HTTP endpoints and delivers schemas for the dynamic UI.
5. `api/static/index.html`
   Provides the desktop-oriented web UI with the wizard and monitoring panels.

## 2. Execution Mode

Current support model:
- Docker-first: officially supported.
- Local Python without Docker: WIP.

## 3. Main Components

### 3.1 `DownloadService`

File: `guaraci/services/downloads.py`

Responsibilities:
- Register sources and expose source metadata (`source`, `title`, `mode`).
- Expose per-source schemas through `get_source_schema`.
- Validate source parameters through `validate_source_params`.
- Run the selected source through `run`.

Adapter types:
- `GovBrDownloadSource` for `gov.br` crawlers (`snis`, `sinisa`)
- `PysusDownloadSource` for PySUS/FTP flows (`sinan`, `sim`, `sih`)
- `OpenDataSUSDownloadSource` for the OpenDataSUS API (`doses_aplicadas_pni`, `zikavirus`)

### 3.2 `DownloadJobService`

File: `guaraci/services/jobs.py`

Responsibilities:
- Create jobs with `create_job`
- Execute jobs in the thread pool with `_run_job`
- Support cancellation and retry
- Persist jobs in `data/jobs/download_jobs.json`
- Expose logs and output metadata per job

## 4. Job Execution Pipeline

1. The UI or API sends `POST /jobs` with `source` and `params`.
2. `DownloadJobService` validates parameters through `DownloadService`.
3. The job enters `queued`.
4. A worker changes the status to `running`.
5. `DownloadService.run()` executes the source with a progress callback.
6. Progress events update percentage, byte counters, ETA, and logs.
7. The job finishes as:
   - `completed` for `success` or `partial_success`
   - `failed` for execution errors or unsuccessful results
   - `canceled`

## 5. Status Semantics

### 5.1 `JobResult` status

Defined in `guaraci/core/results.py`:
- `success`: no failures
- `partial_success`: some failures, but at least one successful download
- `failed`: failures with no successful downloads

### 5.2 Asynchronous job status

Managed by `DownloadJobService`:
- `queued`
- `running`
- `cancel_requested`
- `completed`
- `failed`
- `canceled`

Important rule:
- If `JobResult.status == failed`, the final job status is `failed`, not `completed`.

## 6. Progress Event Model

Main events:
- `download_start`
- `file_start`
- `file_progress`
- `file_completed`
- `file_failed`
- `file_skipped`
- `file_extracted`
- `download_complete`

These events feed:
- percentage progress
- total and downloaded bytes
- current file tracking
- UI log rendering

## 7. Source Pipelines

### 7.1 `gov.br` crawler sources (`snis`, `sinisa`)

- Collect HTML links
- Download raw files
- Optionally extract zip archives
- Generate a manifest in the source output directory

### 7.2 PySUS sources (`sinan`, `sim`, `sih`)

- Download files through PySUS/FTP
- Materialize artifacts in `raw/`
- Optionally export processed datasets when `output_format` is provided
- Include `exported_files` and `export_warning` in the result when relevant

### 7.3 OpenDataSUS sources (`doses_aplicadas_pni`, `zikavirus`)

- Query the OpenDataSUS API with an isolated HTTP client
- Default DEMAS base: `https://apidadosabertos.saude.gov.br`
- Use the local Swagger catalog when source-specific endpoint metadata is available
- `doses_aplicadas_pni` supports:
  - default DEMAS mode
  - optional CKAN mode through `api_base_url`
- `zikavirus` uses the DEMAS flow with the static `/arboviroses/zikavirus` endpoint
- The schema prioritizes native API filters:
  - base: `start_year` and `end_year`
  - optional local refinement: `start_date`, `end_date`, and `uf` when applicable
- `keep_raw` is optional and defaults to `false`
- Optional export uses `csv`, `parquet`, or `sqlite` within the same jobs/UI flow

## 8. Persistence and Recovery

Jobs are persisted as JSON.

When the API restarts:
- previous `queued`, `running`, and `cancel_requested` jobs are marked as interrupted or failed
- the historical record remains available

## 9. Host Folder Mapping in Docker

To improve the "Open Folder" UX:
- the launcher injects:
  - `GUARACI_HOST_APP_ROOT`
  - `GUARACI_CONTAINER_APP_ROOT`
- `jobs.py` translates internal `/app/...` paths to host paths when possible, exposing `host_output_dir`

## 10. Parameter Validation

Contract definitions live in `guaraci/core/contracts.py`:
- per-parameter type (`string`, `integer`, `boolean`, `string_list`)
- required flag
- numeric ranges
- `allowed_values`

Unsupported fields are rejected with HTTP `400` in `POST /jobs`.

## 11. Extensibility

To add a new source:
1. Implement the datasource.
2. Register it in `DownloadService` with `SourceDescriptor` and schema metadata.
3. Add normalization and validation rules.
4. Cover the behavior with tests.
5. Update the API, UI, and filter documentation.

## 12. Current Limitations

- Local Python without Docker remains WIP.
- Availability depends on external source stability, including web and FTP systems.
- The UX still evolves around differences between crawler-based and tabular sources.
