# Internal Architecture

## 1. Overview

Guaraci uses a layered architecture:

1. `datasources`
   Implement data source-specific download and read logic.
   Examples: `SnisDataSource`, `SinisaDataSource`, `SinanDataSource`, `SimDataSource`, `SihDataSource`, `OpenDataSUSDataSource`, `NasaPowerDataSource`, `NasaFirmsDataSource`, `NasaGpmDataSource`, and the IBGE SIDRA datasources (`SidraAggregateSource` base with `IbgePopulacaoDataSource`, `IbgePibMunicipiosDataSource`, `IbgePopulacaoIdadeSexoDataSource`).
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
- `OpenDataSUSDownloadSource` for the OpenDataSUS API (`doses_aplicadas_pni`, `zikavirus`, and generated DEMAS sources)
- `NasaDownloadSource` for keyless/token HTTP APIs — NASA (`nasa_power`, `nasa_firms`, `nasa_gpm`) and IBGE SIDRA (`ibge_populacao`, `ibge_pib_municipios`, `ibge_populacao_idade_sexo`)

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
- Generated DEMAS sources are registered from `guaraci/services/opendatasus_registry.py`
- For generated DEMAS sources:
  - Swagger query parameters are accepted only when declared in the source schema
  - Swagger path parameters are required and substituted into endpoint paths
  - `limit` and `offset` stay internal and are controlled by `batch_size` and pagination
  - API parameters used for the request are persisted in the manifest metadata
- Error handling is contextual:
  - connectivity, timeout, HTTP, configuration, and response-format failures are differentiated in OpenDataSUS client errors
  - datasource-raised errors include endpoint, page, package, or resource context when the failure happened mid-flow
  - manifests persist warning messages such as truncation or export issues

### 7.4 NASA sources (`nasa_power`)

- Query the NASA POWER API through an isolated, keyless HTTP client
  (`guaraci/nasa/client.py`); base: `https://power.larc.nasa.gov`
- Fetch one geographic point (`latitude`/`longitude`) over a date window at
  `daily` or `monthly` resolution
- Parse `properties.parameter.<VAR>.<period>` into a tidy wide table: one row
  per period, one column per requested variable, with derived `date`/`year`/
  `month`/`day` columns
- Read the missing-data sentinel from `header.fill_value` and convert matching
  values to null
- Preserve POWER's monthly annual aggregate losslessly as `month=13`
- `keep_raw` writes the raw JSON response; optional export uses `csv`,
  `parquet`, or `sqlite` within the same jobs/UI flow
- Error handling mirrors OpenDataSUS: connectivity, timeout, HTTP,
  configuration, and response-format failures are differentiated, and the
  manifest persists warnings (empty window, export issues, upstream messages)

### 7.5 NASA FIRMS source (`nasa_firms`)

- Query the NASA FIRMS active-fire CSV endpoints through an isolated client
  (`guaraci/nasa/client.py`); base: `https://firms.modaps.eosdis.nasa.gov`
- Chunk the `[start_date, end_date]` window into consecutive <=10-day requests
  (the FIRMS per-request day-range limit) and concatenate the results
- Parse each CSV generically (robust to MODIS vs VIIRS column sets) and add a
  `firms_product` provenance column
- Select by `country` (ISO3, default `BRA`) or an optional `area` bounding box
  that overrides the country
- Credential handling: the FIRMS `MAP_KEY` is read only from the
  `GUARACI_FIRMS_MAP_KEY` environment variable (never a job parameter, never
  persisted to the manifest); it is also redacted from client error messages
- `keep_raw` writes the raw CSV; optional export uses `csv`, `parquet`, or
  `sqlite` within the same jobs/UI flow

### 7.6 NASA GPM IMERG source (`nasa_gpm`)

- Extract a single grid cell of daily GPM IMERG precipitation per day from the
  GES DISC OPeNDAP server (`gpm1.gesdisc.eosdis.nasa.gov`) using an `.ascii`
  constraint — **no HDF5/NetCDF download or parsing, no heavy dependency**
  (stdlib only), mirroring `nasa_power`'s point-series shape
- One OPeNDAP request per day across the window (capped at ~1 year); the
  OPeNDAP ASCII grid grammar is parsed to a tidy table and the IMERG fill
  sentinel becomes null
- `NasaGesDiscClient` preserves the Earthdata bearer token across the GES DISC
  -> URS OAuth redirect (urllib drops `Authorization` cross-host by default)
- Credential handling: the Earthdata token is read only from
  `GUARACI_EARTHDATA_TOKEN` (never a job parameter, never in the manifest,
  redacted from errors)
- **Experimental:** data access also requires the account to authorize the
  "NASA GESDISC DATA ARCHIVE" application in the Earthdata profile; until then
  data requests return a clean, actionable HTTP 401

### 7.7 IBGE SIDRA sources (`ibge_populacao`, `ibge_pib_municipios`, `ibge_populacao_idade_sexo`)

- Query the IBGE SIDRA v3 aggregates API through an isolated, keyless HTTP
  client (`guaraci/ibge/client.py`); base:
  `https://servicodados.ibge.gov.br/api/v3/agregados`. `IbgeSidraClient`
  decompresses gzip responses (the IBGE CDN sends them intermittently) and
  mirrors the NASA/OpenDataSUS error taxonomy (category / retryable / hint)
- A shared base (`SidraAggregateSource`, `guaraci/ibge/sidra.py`) sweeps one
  year at a time and flattens the SIDRA `resultados -> series -> serie` nesting
  into tidy rows: `nivel, localidade_id, localidade_nome, ano,
  [<classification> …], variavel_id, unidade, valor`
- Each concrete source is a thin subclass pinning a SIDRA table/variable:
  `ibge_populacao` (6579/9324, estimates 2001+), `ibge_pib_municipios`
  (5938/37, municipal GDP 2002+), `ibge_populacao_idade_sexo` (9514/93, census
  2022). The last builds a SIDRA `classificacao` filter from the `sexo` and
  `faixa_etaria` params (classification columns `sexo`, `idade`,
  `forma_de_declaracao_da_idade`)
- `level` selects the territorial aggregation (`municipio`/`uf`/`regiao`/`brasil`
  → SIDRA `N6`/`N3`/`N2`/`N1`); SIDRA missing markers (`-`, `..`) become null and
  a year with no data is skipped with a warning, not a failure
- Registered via the generic `NasaDownloadSource` adapter (mode `ibge api`);
  the orchestrator sweeps them as annual `api_window`s
- No credential required (keyless API)

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


---
? [�ndice da documenta��o](README.md) � [Voltar ao projeto](../README.md)
