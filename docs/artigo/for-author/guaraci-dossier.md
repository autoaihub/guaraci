# Guaraci — Technical and Historical Dossier (current to v0.6.0)

> Factual, citation-ready description of the Guaraci platform, verified against the repository
> (`pyproject.toml`, `CHANGELOG.md`, `docs/ARCHITECTURE.md`, `docs/SOURCES_AND_FILTERS.md`,
> `README.md`) at version **0.6.0**. Written in neutral, descriptive prose suitable for a data
> article (no conclusions/interpretation). Extends the two earlier narratives
> (*Documento Histórico Fundacional*, *Guaraci - historical evolution*), which stopped at v0.4.1.

---

## 1. One-paragraph summary

Guaraci is an open-source (MIT), Docker-first platform that **acquires Brazilian public data
directly from the primary official sources**, decodes legacy formats, harmonizes heterogeneous
schemas, and records full provenance, exposing the result through a CLI, a REST API and a
schema-driven web UI. As of v0.6.0 it integrates **more than 80 sources** across public health
(DATASUS, OpenDataSUS, gov.br) and the environment (NASA), behind a single asynchronous
job-orchestration engine. Its design goal is **reproducible, low-friction access** to data that is
otherwise dispersed across FTP servers, REST APIs and HTML portals in inconsistent, often legacy,
formats.

## 2. Motivation and problem

Brazilian public data — especially in health — is published by different agencies through
incompatible mechanisms and formats:

- **Heterogeneous transport:** FTP servers (DATASUS), REST APIs (OpenDataSUS/DEMAS), and HTML
  portals (gov.br).
- **Legacy formats:** compressed `.dbc` and `.dbf` microdata (DATASUS), plus CSV/XLSX/JSON.
- **Schema drift:** table layouts change across years and across diseases for the same system.
- **Operational instability:** government FTP servers and APIs are frequently unavailable.
- **No standard access layer:** every consumer re-implements brittle extraction/ETL code.

Guaraci was created within the **AutoAI-Pandemics** project (ICMC-USP) to remove this barrier so
that epidemiologists and data scientists spend effort on analysis rather than data plumbing,
starting from the study of **Neglected Tropical Diseases** (SINAN) and broadening to a general
multi-source acquisition platform. A guiding rule is the **primary-source principle**: data is
always taken from the official publisher, never from curated third-party mirrors (e.g., Base dos
Dados, microdatasus, PCDaS), even when those expose more convenient query layers.

## 3. Evolution timeline (0.1.x → 0.6.0)

| Version | Milestone |
|---|---|
| **0.1.x** (legacy) | Experimental prototype: unstructured scripts; first attempts to parse DATASUS `.dbc`; environment-dependent (Micromamba); dependency/OS-portability problems exposed. |
| **0.2.0** | First modular structure; **Docker introduced as policy**; first SINAN integration; `core` layer; first automated tests. Reproducibility promoted to a requirement. |
| **0.3.0** | DATASUS expansion to **SIM** and **SIH**; dedicated CLIs; standardized export to **CSV/Parquet/SQLite**. |
| **0.4.0** | **Paradigm shift to infrastructure:** `DownloadService` + `DownloadJobService` (asynchronous jobs, progress, retry, cancellation, disk persistence); schema-driven UI; SNIS consolidated as a gov.br crawler; **legacy SNIS BigQuery moved to legacy** (primary-source principle); unknown-parameter validation returns HTTP 400. |
| **0.4.1** | **OpenDataSUS REST integration** (`doses_aplicadas_pni`, `zikavirus`); isolated HTTP client; native year filters + optional local refinements; optional export. Platform now spans FTP + crawler + REST. |
| **0.5.0** | OpenDataSUS epidemiological sources elevated to first-class (`mpox`, `esavi`, `dengue`, `chikungunya`, `srag_demas`, `sindrome_gripal_leve`, `febre_amarela`); **auto-generated DEMAS source registry** from a local Swagger catalog; manifest schema **v1.1** (`materialized_paths`, `exported_files`, `warnings`, `request.filters`); schema `phase` field for UI grouping; non-retryable retry guard. |
| **0.5.1** | PySUS 2.x Docker/Linux integration fix (`libmagic1`). |
| **0.5.2** | SIH discovery fixes + preflight; **DATASUS direct-FTP backend** (phases 1–4) made the default (PySUS → opt-in). |
| **0.6.0** | **NASA** POWER / FIRMS / GPM IMERG environmental sources; **11 additional DATASUS systems via direct FTP** (phase 5); generic schema-driven **`guaraci fetch`** CLI (`list`/`schema`/`run`/`discover`/`fields`); **per-source data dictionary** (`docs/DATA_DICTIONARY.md`) from live sampling; BigQuery (legacy SNIS) moved to the optional `snis-legacy` extra; repository cleanup + adoption of the Vogel Stack work-board. |

## 4. Architecture (layered)

Guaraci uses a five-layer architecture (see `docs/ARCHITECTURE.md`):

1. **`datasources/`** — source-specific download/read logic. Implementations include
   `SnisDataSource`, `SinisaDataSource`, `SinanDataSource`, `SimDataSource`, `SihDataSource`,
   `OpenDataSUSDataSource`, `NasaPowerDataSource`, `NasaFirmsDataSource`, `NasaGpmDataSource`, and
   the spec-driven `FtpDataSource` for the phase-5 systems.
2. **`services/downloads.py` (`DownloadService`)** — the **source registry**: declares each
   source's schema, validates and normalizes parameters (rejecting unknown ones), and adapts
   source output to a unified `JobResult`. Adapter types: `GovBrDownloadSource`,
   `PysusDownloadSource`, `OpenDataSUSDownloadSource`, `NasaDownloadSource`, and the FTP source
   builder for the phase-5 systems.
3. **`services/jobs.py` (`DownloadJobService`)** — asynchronous engine: creates and runs jobs in a
   thread pool, tracks status/progress, supports cancellation and retry, persists state to
   `data/jobs/download_jobs.json`, and exposes per-job logs and output metadata.
4. **`api/main.py`** — FastAPI HTTP layer (`/health`, `/sources`, `/sources/{source}/schema`,
   `POST /sources/{source}/discovery`, `/jobs`, `/jobs/{id}/logs`, `/jobs/{id}/output`, …).
5. **`api/static/index.html`** — desktop-oriented web UI with a schema-driven wizard and job
   monitoring. (A newer React UI under `apps/web/` coexists.)

**Job lifecycle:** `POST /jobs` → validation via `DownloadService` → `queued` → `running` →
`DownloadService.run()` with a progress callback → terminal `completed` / `failed` / `canceled`.
`JobResult` status is `success`, `partial_success`, or `failed`; a `failed` result forces a
`failed` job. **Progress events:** `download_start`, `file_start`, `file_progress`,
`file_completed`, `file_failed`, `file_skipped`, `file_extracted`, `download_complete` — feeding
percentage, byte counters, current-file tracking, ETA, and structured logs.

**Parameter contracts** (`guaraci/core/contracts.py`): per-parameter type
(`string`/`integer`/`boolean`/`string_list`), required flag, numeric ranges, and `allowed_values`;
unknown fields are rejected with HTTP 400.

## 5. Acquisition mechanisms (four transports, one contract)

Guaraci abstracts four acquisition mechanisms behind the same schema/validation/JobResult contract:

- **HTML crawler (gov.br)** — `snis`, `sinisa`: collect links, download raw files, optionally
  extract zip archives, write a manifest.
- **REST API (OpenDataSUS / DEMAS)** — isolated HTTP client (`guaraci/opendatasus/client.py`);
  default DEMAS base `apidadosabertos.saude.gov.br`; native year filters with optional local
  refinement (`start_date`/`end_date`/`uf`); internal pagination (`batch_size`/`max_pages`);
  generated DEMAS sources substitute path parameters and pass only declared query parameters;
  request metadata (`api_params`) recorded in the manifest. Error taxonomy distinguishes
  connectivity, timeout, HTTP, configuration, and response-format failures.
- **Direct DATASUS FTP** — anonymous `ftplib` connection to `ftp.datasus.gov.br`; decodes `.dbc`
  via `pyreaddbc` (→`.dbf`) + `dbfread` (→records→Polars), and plain `.dbf` directly (PNI). This
  **replaced the PySUS backend** as default in v0.5.2, cutting ~20 transitive dependencies to 2
  while keeping the same primary source. Backend selectable via `GUARACI_DATASUS_BACKEND={ftp|pysus}`.
- **NASA APIs (environment)** — keyless **POWER** (`power.larc.nasa.gov`); **FIRMS** active-fire CSV
  (`firms.modaps.eosdis.nasa.gov`, free MAP_KEY); **GPM IMERG** daily precipitation via GES DISC
  **OPeNDAP point subsetting** (`.ascii` constraint — no HDF5/NetCDF download/parsing, stdlib only).
  All three are implemented with **no new runtime dependency**.

## 6. Source coverage (v0.6.0)

Over **80 registered sources** in total — 28 first-class named sources below, plus dozens of
auto-generated OpenDataSUS DEMAS endpoints derived from a local Swagger catalog.

- **gov.br crawler (2):** `snis`, `sinisa`.
- **OpenDataSUS REST (9 named + generated DEMAS):** `doses_aplicadas_pni`, `zikavirus`,
  `febre_amarela`, `mpox`, `esavi`, `dengue`, `chikungunya`, `srag_demas`, `sindrome_gripal_leve`
  + generated DEMAS sources (e.g., `cnes_estabelecimentos`, `sisagua_*`).
- **DATASUS FTP, mode `pysus ftp` (3):** `sinan`, `sim`, `sih` (direct-FTP backend by default;
  PySUS opt-in).
- **DATASUS direct FTP, mode `datasus ftp` (11, phase 5):** `sinasc` (live births), `sia`
  (outpatient), `cnes` (health facilities), `pni` (historical immunization, `.DBF`), `ciha`,
  `cih` (legacy 2008–2010), `siscan` (cervical/breast cancer screening), `sisprenatal`
  (prenatal care), `resp` (Zika-related notifications), `pce`, `painel_oncologia` (oncology panel).
- **NASA (3):** `nasa_power` (climate/meteorology), `nasa_firms` (active fire), `nasa_gpm`
  (precipitation, experimental — requires authorizing the GES DISC archive app).

All FTP systems support a **discovery preflight** (`POST /sources/{source}/discovery` or
`guaraci datasus discover`) returning file counts by group/UF **without downloading** — important
before pulling large systems such as SIA. The `mode` field describes transport, not publisher
(`pysus ftp` is kept as a stable contract label even though the default fetch layer is now direct FTP).

## 7. Data engineering

- **Decoding:** `.dbc`→`.dbf`→records→Polars via `pyreaddbc`+`dbfread`; plain `.dbf` handled
  directly; Polars used for out-of-core/chunked processing of files exceeding RAM.
- **Schema harmonization:** conservative **union of all historical columns** (not intersection),
  null-padding missing fields, to preserve every variable ever published across years/diseases.
- **Output formats:** CSV, Parquet, SQLite; raw artifacts materialized under `<output_dir>/raw/`.
- **Provenance:** a standardized **`manifest.json` (v1.1)** per run records source, request
  filters, materialized/exported paths, warnings, and (for APIs) `api_params`.
- **Idempotent, delta-aware collection:** re-runs skip files already materialized; the FTP
  discovery preflight compares volumetry (file count/size) to fetch only what is new or changed.
- **Tidy NASA output:** point series as wide tables (one row per period; derived
  `date`/`year`/`month`/`day`); upstream fill sentinels converted to null; POWER monthly annual
  aggregate preserved losslessly as `month=13`.

## 8. Reproducibility

- **Docker-first** is the only officially supported workflow; local Python without Docker is WIP.
  Encapsulating the runtime removes "works on my machine" failures (Python version, native
  dependencies such as `psycopg2`, FTP-library behavior on Windows vs Linux).
- **Few, pinned dependencies:** core stack is Polars, PyArrow, Pydantic v2, Click, Rich, Loguru;
  optional extras (`datasus`, `api`, `viz`, `docs`, `datasus-legacy`) keep installs minimal.
- **Stable output contract:** standardized export layout + manifest lets downstream pipelines
  depend on a fixed interface regardless of the upstream transport.

## 9. Governance and security

- **AI-agent governance (`AGENTS.md`, `docs/AI_HANDOFF_OPENDATASUS.md`):** explicit rules for
  agents/contributors — do not break existing source contracts; preserve the Docker-first flow;
  update tests **and** documentation in the same change; reject unknown parameters; basic filters
  map to native API queries while local refinements stay in advanced controls.
- **Credential handling:** API credentials (FIRMS `MAP_KEY`, Earthdata token) are read **only**
  from environment variables (`GUARACI_FIRMS_MAP_KEY`, `GUARACI_EARTHDATA_TOKEN`) — never job
  parameters (which are persisted to disk), never written to manifests, and redacted from error
  messages.
- **Testing:** a comprehensive automated suite (hundreds of tests) plus opt-in live smoke tests
  (`GUARACI_FTP_SMOKE=1`, `GUARACI_FTP_SMOKE` phase-5) that validate decoding against the real
  servers. New modules are mypy-clean.

## 10. Limitations (data-collection/curation, descriptive)

- Local Python execution without Docker remains WIP/unsupported.
- Availability depends on external server stability (DATASUS FTP, government APIs).
- Historical coverage windows differ by system.
- Bit-exact parity vs the legacy PySUS backend was **not** formally verified before the default
  flip (reversible via one environment variable).
- Retry lacks automated exponential backoff; aggregate per-source observability is limited.
- `nasa_gpm` is experimental (requires authorizing the GES DISC archive application).
- Source notification data may carry under-reporting/entry lag at the origin (inherent to the
  source, not the platform).

## 11. Future directions

Expanded source coverage; municipality-centroid lookup for NASA point series (needs an IBGE
coordinate dataset); distributed job execution; fuller FAIR metadata + automated data
dictionaries; exponential-backoff retry and per-source observability.

## 12. Quick fact sheet

| Field | Value |
|---|---|
| Version | 0.6.0 (Alpha) |
| License | MIT |
| Language / stack | Python 3.11–3.12; Polars, PyArrow, Pydantic v2, Click, Rich, Loguru; FastAPI (API) |
| Interfaces | CLI (`guaraci`), REST API (FastAPI), schema-driven web UI |
| Sources | >80 (health: DATASUS, OpenDataSUS, gov.br; environment: NASA) |
| Formats in | `.dbc`, `.dbf`, CSV, XLSX, JSON, FTP/REST/HTML |
| Formats out | CSV, Parquet, SQLite + `manifest.json` (v1.1) |
| Repository | https://github.com/autoaihub/guaraci |
| Context / funding | AutoAI-Pandemics (ICMC-USP); AI4PEP network; IDRC (Canada) |
