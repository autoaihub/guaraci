# Changelog

## [Unreleased]

### Added — IBGE registro civil + território (Fase C)
- `ibge_nascidos_vivos_rc` (`guaraci/ibge/registro_civil.py`) — live births by
  month/sex, SIDRA table 2680 (variable 218), registro civil; a counterpoint
  to DATASUS SINASC. Reference verified live 2026-08-17: Brasil 2023,
  `mes`/`sexo`=`total` → 2 523 267.
- `ibge_obitos_rc` — deaths by month/sex, SIDRA table 2681 (variable 343),
  registro civil; counterpoint to DATASUS SIM. Reference verified live
  2026-08-17: Brasil 2023, `mes`/`sexo`=`total` → 1 429 575.
- `ibge_area_territorial` (`guaraci/ibge/territorio.py`) — area / density /
  population from SIDRA table 4714 (variables 93/614/6318 bundled in one
  request via SIDRA's `|`-joined variable list), single period 2022 (census
  reference). Reference verified live 2026-08-17: Brasil área territorial
  8 510 417.771 km².
- Both registro-civil sources reject `mes != "total"` at `level="municipio"`
  up front (`ValueError`) — confirmed live that SIDRA returns HTTP 500 for the
  municipal x all-months combination (5570 municipalities x 13 categories
  exceeds the aggregate limit); UF/região/Brasil accept the monthly
  breakdown.
- Registered in `guaraci/services/sources/ibge.py` (mode `ibge api`); backfill
  floors added to `ibge_floor` in `guaraci/orchestrator/cadence.py` (2003 for
  both registro-civil sources, 2022 — census year — for área territorial).
- Offline tests in `tests/test_ibge_registro_civil_territorio.py` (fake SIDRA
  client) plus 3 new opt-in live smoke tests in `tests/test_ibge_smoke.py`
  (`GUARACI_IBGE_SMOKE=1`).
- Site catalog, `docs/SOURCES_AND_FILTERS.md` and `field_dictionary.json` /
  `docs/DATA_DICTIONARY.md` updated for the 3 new sources; source count in
  the site copy raised from 91 to 94.

### Added — versioned SIH-RD column mapping
- Added `DEFAULT_SIH_RD_COLUMN_MAP` and `apply_sih_column_map()` / `SihDataSource.apply_column_map()` in `guaraci/datasus/sih.py` for standardizing SIH-RD field names (`N_AIH` -> `numero_aih`, `DT_INTER` -> `data_internacao`, `MUNIC_RES` -> `municipio_residencia`, `DIAG_PRINC` -> `diagnostico_principal`, etc.), backed by unit regression tests in `tests/test_sih_column_map.py`.

### Added — Vogel Stack compliance CI workflow
- Added `.github/workflows/vogel_stack_ci.yml` running `check-wikilinks.ps1` and `check-quadro.ps1` on every push/PR for automated Vogel Stack compliance verification.

### Changed — legacy web app structure
- Moved `apps/web` to `legacy/apps/web`, isolating the legacy React frontend out of core installable packages and consolidating CLI-first workflow guidelines.

### Added — public properties on JobResult contract
- Promoted `JobResult.exported_files` and `JobResult.materialized_paths` as explicit, version-stable public properties on `JobResult` (`guaraci/core/results.py`), freezing the interface seam consumed downstream by Monitoramento and external scripts.

### Changed — Polars deprecation sweep
- Replaced all deprecated `df.groupby(...)` calls with `df.group_by(...).len()` in `sih.py`, `sim.py`, and `sinan.py` summary methods.

### Changed — field dictionary & catalog sampling updates
- Successfully sampled and cataloged 5 pending sources (`pni`, `siscan`, `pce`, `cnes_estabelecimentos_{codigo_cnes}`, `cnes_tipounidades_{codigo_tipo_unidade}`), raising the total of fully-sampled sources from 72 to 77 in `guaraci/data/field_dictionary.json` and `docs/DATA_DICTIONARY.md`.

### Changed — web UI restyled with the Guaraci visual identity
- `guaraci/api/static/index.html` now uses the dark "amanhecer de dados" theme
  from the project site (Space Grotesk/Inter/JetBrains Mono, sun-orange +
  teal palette, gradient progress bar, dark log console, inline Guaraci logo).
  Purely presentational: all element ids/classes consumed by the embedded JS
  and every API contract (`/sources`, `/sources/{s}/schema`, `/jobs`,
  `/jobs/{id}/logs`) are unchanged. Verified end-to-end against the live API
  (schema-driven wizard, job creation, progress, logs, history).

### Added — documentation site with the full 91-source catalog
- `site/docs.html` + `site/assets/docs.js`: extensive user guide (install,
  web UI, `guaraci fetch`, output formats, NASA credentials, orchestrator,
  best practices) plus a generated catalog documenting every source — all
  parameters (type, phase, default, allowed values), live-sampled fields, and
  a ready-to-copy CLI example per source.
- `scripts/build_site_catalog.py` generates `site/assets/catalog-data.js` from
  `DownloadService` schemas + `guaraci/data/field_dictionary.json` +
  orchestrator cadence profiles; `--live` adds real FTP discovery counts
  (14 DATASUS systems verified against `ftp.datasus.gov.br`).
- Landing page explorer cards now open a per-source detail modal linking into
  the docs page (single data source: `catalog-data.js` replaces `bases.js`).

### Added — IBGE connectors (SIDRA aggregates API, keyless JSON)
- New `guaraci/ibge/` package with a shared `SidraAggregateSource` base (fetch
  one year at a time, flatten `resultados -> series -> serie` into tidy rows,
  export/manifest) and three curated sources — the denominator / socioeconomic
  layers for turning DATASUS counts into rates:
  - `ibge_populacao` — population estimates by locality x year (table 6579).
  - `ibge_pib_municipios` — municipal GDP / PIB in R$ 1000 (table 5938, 2002+).
  - `ibge_populacao_idade_sexo` — census population by sex and age (table 9514;
    `sexo` and `faixa_etaria` params, default 5-year age groups by sex per UF).
- Output is one row per (locality, year[, classification]); missing markers
  (`-`, `..`) become null; a year with no data is skipped with a warning, not a
  failure. The client decompresses gzip responses (the IBGE CDN sends them
  intermittently) and supports SIDRA classification filters.
- All three are registered in `DownloadService` (mode `ibge api`), reachable
  from the API, `guaraci fetch`, and the orchestrator (annual `api_window`, with
  per-table backfill floors: 2001 / 2002 / 2022). Tests: `tests/test_ibge.py`
  (18, offline) + opt-in live smoke `tests/test_ibge_smoke.py`
  (`GUARACI_IBGE_SMOKE=1`).
- Docs: `README.md`, `docs/SOURCES_AND_FILTERS.md` (§2 + §3.12–3.14),
  `docs/ARCHITECTURE.md` (§1, §3.1, §7.7), `docs/DATA_DICTIONARY.md` (three
  `ibge_*` entries, live-sampled), `guaraci/data/field_dictionary.json`,
  `docs/AI_HANDOFF_OPENDATASUS.md` (§1), `docs/operacao.md` (§2).

### Added — bronze orchestrator (`guaraci orchestrate`)
- New `guaraci/orchestrator/` package + `guaraci orchestrate` CLI that sweeps
  every registered source into a browsable **bronze** tree of raw CSVs at each
  source's **native granularity**, recording one row per partition in an
  append-only CSV **ledger** (`<bronze_root>/_ledger.csv`). This is the
  automation layer that feeds the Sabiá data lake.
- Two bronze tiers, written from a single decode of each file: `raw` (the
  official file as-is, native granularity) and `refined` (the same rows
  repartitioned into the browsable `disease/year/month` tree — annual sources
  split by their event date with an unknown-month bucket, monthly sources pass
  through). `refined` is still bronze (a pure repartition, no harmonisation);
  select with `--tier raw|refined|both` (default both).
- Modes: `orchestrate backfill` (full history, "sair tudo"), `orchestrate
  update` (incremental delta driven by the ledger, with a `src_size` volumetria
  check so a grown current-year file is re-pulled), plus `plan` (dry-run),
  `profiles` (resolved per-source kind/cadence) and `status` (read the ledger).
- Each source resolves to a `SourceProfile` (kind + publication **cadence** +
  backfill floor): SINAN/SIM/SIH + the 11 FTP systems discover at file level
  (1 DATASUS file = 1 bronze CSV); OpenDataSUS sweeps by year; NASA is marked
  on-demand (needs a lat/lon) and skipped by the sweep.
- FTP materialisation downloads a source's whole batch over one connection
  straight from each file's known path (no re-listing), reusing the idempotent
  parquet cache, then writes each raw file out as its own CSV.
- Thin cron entrypoints in `scripts/server/` (`orchestrate.sh` + `orchestrate.ps1`,
  with a lock + per-day log). Docs: `docs/ORCHESTRATOR.md`. Tests:
  `tests/test_orchestrator.py` (22, offline) + opt-in live smoke
  `tests/test_orchestrator_smoke.py` (`GUARACI_FTP_SMOKE=1`).

### Changed — DATASUS sources can now collect the in-progress current year
- The DATASUS microdata sources (SIH, SIM, SINAN, and the 11 spec-driven FTP
  systems) previously capped collection at the last complete year
  (`current_year - 1`), in both the parameter schema (`maximum`) and the
  runtime year resolution. They now accept the current year as well, so a
  surveillance pipeline can pull the in-progress season (e.g. requesting
  `end_year=2026` during 2026). Only genuinely future years are clamped, back
  to the current year (was: silently reduced to `current_year - 1`).
- Defaults are unchanged (`default=last_year`), so callers that don't override
  the range still get the last complete year. Current-year data is logged as
  potentially partial, reflecting the DATASUS publication lag (~2–3 months).
- Other sources (NASA, OpenDataSUS, gov.br) already allowed the current year;
  this aligns the DATASUS FTP layer with them.

## [0.6.0] - 2026-06-28

### Added — source validation + data dictionary (`fetch fields`)
- `scripts/sample_sources.py` samples each source with tiny windows to validate it
  works and capture (a) filter parameters and (b) output field names. Results are
  shipped as `guaraci/data/field_dictionary.json` + `docs/DATA_DICTIONARY.md` (88
  sources cataloged; 19 field-sampled). New `guaraci fetch fields <source>` prints
  the known output field names for a source.
- Findings surfaced by the live sampling (flagged for follow-up): `pni`/`pce`/`siscan`
  return empty with a `group=None` warning in `load_dataframe` (multi-group/national
  load path); `mpox` returned an upstream DEMAS HTTP 500; NASA FIRMS/GPM need
  credentials. The SIH field set was confirmed real (`DT_INTER`/`DT_SAIDA`/`MUNIC_RES`/
  `DIAG_PRINC` present), validating the Monitoramento ingest column map.

### Added — generic `guaraci fetch` CLI (schema-driven, all sources)
- New `guaraci/cli/fetch_cli.py` registering a `fetch` command group: `fetch list`
  (every registered source), `fetch schema <source>` (its parameter schema),
  `fetch run <source> --set KEY=VALUE … [--format csv|parquet|sqlite] [-o DIR]`,
  and `fetch discover <source> --set … [--sizes]` (FTP preflight: file count by
  group/UF, plus the total download size with `--sizes`, without downloading).
  It drives `DownloadService`, so OpenDataSUS, NASA and gov.br sources are now
  reachable from the CLI (previously only via the API/UI) with no per-source code.
  `--set` values are coerced to the schema-declared type; `--format` is optional
  (omit for download-only); NASA credentials stay environment-only. Tests:
  `tests/test_fetch_cli.py`.
- `DownloadService.discover()` now accepts a keyword-only `fetch_sizes` flag and
  forwards it to the FTP datasource, so the preflight can report the total
  download size (backward-compatible; default `False`).

### Changed — legacy SNIS BigQuery deps moved to an optional `snis-legacy` extra
- `google-cloud-bigquery` and `db-dtypes` moved out of the core dependencies (and
  out of `requirements.txt`) into a new optional extra `snis-legacy`, so
  `pip install guaraci` / `guaraci[datasus]` no longer pulls the Google stack.
  They are only needed for the legacy SNIS BigQuery path (`snis download-legacy`),
  which imports them lazily and now points users to `pip install "guaraci[snis-legacy]"`.
  The `full` extra still includes them.

### Added — NASA POWER climate source (`nasa_power`)
- New `guaraci/nasa/` package integrating the NASA POWER API directly
  (`power.larc.nasa.gov`, no authentication), honoring the primary-source
  principle: `NasaPowerClient` (stdlib `urllib`, OpenDataSUS-style error
  taxonomy) and `NasaPowerDataSource` (single-point daily/monthly series).
- Registered the `nasa_power` source (`mode = "nasa power api"`) through a new
  `NasaDownloadSource` adapter in `guaraci/services/downloads.py`, with a
  schema-driven parameter set (`latitude`, `longitude`, `start_date`,
  `end_date`, `parameters`, `temporal`, `community`, `keep_raw`, `timeout`,
  `api_base_url`, `output_dir`, `output_format`) and `_normalize_nasa_power_params`.
- Output is a tidy wide table (one row per period, one column per POWER
  variable) with derived `period`/`date`/`year`/`month`/`day` and point
  columns; the `header.fill_value` sentinel is converted to null and POWER's
  monthly annual aggregate is preserved losslessly as `month=13`.
- Exports to `csv`/`parquet`/`sqlite`, writes a standard `DownloadManifest`,
  and emits `download_start`/`file_completed`/`download_complete` progress
  events compatible with `DownloadJobService`.
- Tests: `tests/test_nasa_power_client.py`, `tests/test_nasa_power_datasource.py`,
  `tests/test_nasa_power_service.py`, plus a NASA POWER schema check in
  `tests/test_api.py` (39 new datasource/client/service tests).
- Docs: `README.md`, `docs/ARCHITECTURE.md` (§3.1, §7.4),
  `docs/SOURCES_AND_FILTERS.md` (§2, §3.9).

### Notes
- No new runtime dependency: the client uses only the standard library.
- `latitude`/`longitude` are the native point inputs; municipality-centroid
  lookup is deferred as future work (needs an IBGE coordinate dataset).
- The curated `parameters` allow-list is a subset of the full POWER catalogue,
  chosen for public-health/environmental cross-analysis and validated live.

### Added — NASA FIRMS active-fire source (`nasa_firms`)
- `NasaFirmsClient` (in `guaraci/nasa/client.py`) and `NasaFirmsDataSource`
  (`guaraci/nasa/firms.py`) integrating the NASA FIRMS active-fire CSV API
  (`firms.modaps.eosdis.nasa.gov`) directly. No new runtime dependency.
- Registered the `nasa_firms` source (`mode = "nasa firms api"`) via the shared
  `NasaDownloadSource` adapter + `_normalize_nasa_firms_params`. Schema:
  `start_date`, `end_date`, `product` (FIRMS source product; curated
  allow-list), `country` (ISO3, default `BRA`), `area` (optional bounding-box
  override), `keep_raw`, `timeout`, `api_base_url`, `output_dir`,
  `output_format`.
- The `[start_date, end_date]` window is chunked into consecutive <=10-day
  FIRMS requests; each CSV is parsed generically (robust to MODIS vs VIIRS
  columns), concatenated, and tagged with a `firms_product` provenance column.
- **Security:** the FIRMS `MAP_KEY` is read only from the
  `GUARACI_FIRMS_MAP_KEY` environment variable — never a job parameter (job
  params are persisted to disk) and never written to the manifest; it is also
  redacted from client error messages.
- The user-facing parameter is named `product` (not `source`) to avoid
  colliding with `DownloadService.run(source, **params)`.
- Tests: `tests/test_nasa_firms_client.py`, `tests/test_nasa_firms_datasource.py`,
  `tests/test_nasa_firms_service.py`, plus a FIRMS schema check in
  `tests/test_api.py` (29 new tests).
- Docs: `README.md`, `docs/ARCHITECTURE.md` (§1, §3.1, §7.5),
  `docs/SOURCES_AND_FILTERS.md` (§2, §3.10).
- Live-unvalidated pending a free MAP_KEY (mock-tested only); endpoint paths and
  CSV handling follow the documented FIRMS API.

### Added — NASA GPM IMERG precipitation source (`nasa_gpm`)
- New `NasaGesDiscClient` (in `guaraci/nasa/client.py`) and `NasaGpmDataSource`
  (`guaraci/nasa/gpm.py`) integrating GES DISC GPM IMERG daily precipitation via
  **OPeNDAP point subsetting** — one grid cell per day through an `.ascii`
  constraint, so it never downloads or parses HDF5/NetCDF and adds **no new
  runtime dependency** (stdlib only), mirroring `nasa_power`'s point-series shape.
- Registered the `nasa_gpm` source (`mode = "nasa gpm api"`) via the shared
  `NasaDownloadSource` adapter + `_normalize_nasa_gpm_params`. Schema:
  `latitude`, `longitude`, `start_date`, `end_date`, `variable` (curated IMERG
  variables), `product` (`daily`), `keep_raw`, `timeout`, `api_base_url`,
  `output_dir`, `output_format`. The window is capped at ~1 year (one request
  per day).
- The client preserves the EDL bearer token across the GES DISC -> URS OAuth
  redirect (urllib drops `Authorization` cross-host by default), converts the
  IMERG fill sentinel to null, and parses the OPeNDAP ASCII grid grammar.
- **Security:** the Earthdata token is read only from the
  `GUARACI_EARTHDATA_TOKEN` environment variable — never a job parameter (job
  params are persisted to disk), never written to the manifest, and redacted
  from client error messages.
- **EXPERIMENTAL / live-data-unvalidated:** the OPeNDAP contract (endpoint,
  granule naming, grid layout, index formula, ASCII grammar) was validated with
  a real Earthdata token, but a successful *data* response also requires the
  account to authorize the "NASA GESDISC DATA ARCHIVE" application at
  urs.earthdata.nasa.gov; until then data returns a clean, actionable HTTP 401.
  The parser/pipeline are covered by tests against the documented ASCII format.
- Tests: `tests/test_nasa_gpm_client.py`, `tests/test_nasa_gpm_datasource.py`,
  `tests/test_nasa_gpm_service.py`, plus jobs-integration and an API schema check
  (30 new tests). Docs: `README.md`, `docs/ARCHITECTURE.md` (§3.1, §7.6),
  `docs/SOURCES_AND_FILTERS.md` (§2, §3.11).

## [0.5.2] - 2026-05-28

### Entradas principais
- Updated `vogel-stack` submodule to VogelStack commit `d54e529`, including the automatic-commit workflow rule and nested-vault README wikilinks.
- Documented Guaraci's closing protocol for generic sync commits in `AGENTS.md`, `docs/versionamento.md`, and `docs/operacao.md`.
- Published the submodule README wikilink adaptation while keeping the new upstream Graphify discovery section.
- Fixed SIH discovery to use the PySUS FTP catalog directly and require `pysus[dbc]` for DBC-to-Parquet conversion in Docker builds.
- Added SIH discovery preflight and made empty SIH `groups`/`months` selections mean unfiltered; removed redundant SIH `mes` from the jobs/UI schema.

### Estado
- Verification: documentation diff reviewed locally; SIH runtime verification is listed below.
- SIH verification: FTP discovery was checked against the JP filter set without downloading the full dataset, and focused unit tests were run locally.
- Still unsupported: local Python execution without Docker remains WIP.
- Operational note: `vogel-stack` commit `d54e529` was pushed before syncing/pushing the Guaraci parent repository.

### DATASUS: direct-FTP backend (phases 1-4)
- Added a direct DATASUS FTP layer under `guaraci/datasus/ftp/` (`client`, `catalog`, `discovery`, `dbc`, shared `orchestration`, and per-source `sih_backend`/`sim_backend`/`sinan_backend`) built on stdlib `ftplib` + `pyreaddbc`/`dbfread`, replacing the ~20 transitive dependencies of `pysus[dbc]` with 2 packages while keeping the same primary source (`ftp.datasus.gov.br`).
- SIH, SIM, and SINAN now select their backend via `GUARACI_DATASUS_BACKEND={ftp|pysus}`, resolved by the shared dependency-free selector `guaraci/datasus/backend.py`.
- **Default backend flipped to `ftp`** (phase 4): the `datasus` extra now installs only `pyreaddbc` + `dbfread`. The legacy PySUS path stays installable for one release via the new `datasus-legacy` extra and selectable via `GUARACI_DATASUS_BACKEND=pysus`. This supersedes the earlier same-version note above about requiring `pysus[dbc]` in Docker builds.
- Bumped the PySUS pin to `pysus>=2.2.0` (the obsolete `[dbc]` extra was folded into the base package upstream and now warns on `uv lock`).
- API/CLI/UI contracts unchanged: the `mode` descriptor for SIH/SIM/SINAN remains `pysus ftp` and the parquet output schema is identical.

### Estado (direct-FTP migration)
- Tests: full suite 319 passed, 3 skipped (opt-in live FTP smoke + Docker-specific). The two failures in `tests/test_sinan_datasource.py` (`test_sinan_download_uses_single_worker`, `test_download_file_safe_closes_ftp_singleton`) are pre-existing — they reference `ThreadPoolExecutor`/`_download_file_safe`, already absent from `sinan.py` before this branch — and are unrelated to this migration; flagged for separate cleanup.
- Gates pendentes: bit-exact parity vs PySUS and 1 week of opt-in production validation were NOT met before the default flip; the flip was authorized anyway and is reversible via a single env var (`GUARACI_DATASUS_BACKEND=pysus`) or by reverting `DEFAULT_BACKEND` in `guaraci/datasus/backend.py`.

### DATASUS: 11 more systems via direct FTP (phase 5)
- Extended the direct-FTP integration beyond SIH/SIM/SINAN to eleven more DATASUS microdata systems: `sinasc`, `sia` (SIA-SUS ambulatorial), `cnes`, `pni` (historical SI-PNI), `ciha`, `cih`, `siscan`, `sisprenatal`, `resp`, `pce`, and `painel_oncologia`. All FTP-only (no PySUS legacy path).
- New spec-driven engine: `guaraci/datasus/ftp/specs.py` (one `SystemSpec` per system — filename regex + FTP paths + dimension flags), a generic `discover_spec`, plain-`.DBF` decoding in `dbc.py` (PNI ships uncompressed DBF), and `generic_backend`. Paths and group sets (SIA's 14 groups, CNES's 13, PNI's CPNI/DPNI) were confirmed by live FTP recon, not guessed.
- One generic `FtpDataSource` (parametrised by spec) plus registration of all eleven as platform sources (`mode = "datasus ftp"`), reachable via `/sources`, `/sources/{source}/schema`, `/jobs`, the UI, and a new generic `guaraci datasus` CLI (`list` / `download` / `discover`).
- Discovery preflight extended to all eleven (file count + by-group/by-state, no download) via `POST /sources/{source}/discovery`, `DownloadService.discover()`, and `guaraci datasus discover` — important before pulling large systems like SIA. `fetch_sizes` is off by default so the preflight never issues thousands of `SIZE` round-trips.
- Tests: ~70 offline tests (specs, discovery layouts/dispatch, DBF decode, generic backend, datasource, registry, CLI, API) plus an opt-in live smoke (`tests/test_ftp_smoke_phase5.py`, `GUARACI_FTP_SMOKE=1`) that downloads+decodes the oncology panel (`.dbc`) and PNI (`.DBF`) against the real server. Full suite is green; the previously-failing stale `tests/test_sinan_datasource.py` tests were rewritten to cover the current legacy path, and the new modules are mypy-clean.
- Scope/exclusions: collection params only for now (no per-field export refinements yet); `CMD` (no accessible microdata on the FTP) and `ANS` (private-insurance, out of public-health-microdata scope) were deliberately excluded.

## [0.5.1] - 2026-05-26

### Fixed
- PySUS 2.x Docker Linux integration by adding `libmagic1` system dependency to `Dockerfile`.
- Confirmed PySUS 2.1.0 compatibility with Guaraci async client functions.

### Changed
- Project version updated to `0.5.1`

## [0.5.0] - 2026-05-22

### Added
- OpenDataSUS sources `mpox`, `esavi`, `dengue`, `chikungunya`, `srag_demas`, `sindrome_gripal_leve`, and `febre_amarela` elevated to first-class epidemiological sources with start/end year enforcement and local filtering
- Auto-generated DEMAS source registry from local Swagger catalog (`guaraci/services/opendatasus_registry.py`)
- Generic DEMAS download path with query parameter passthrough and path parameter substitution
- `phase` field on `SourceParameterSpec` and `SourceParamResponse` for schema-driven UI grouping
- `error_retryable` flag on `DownloadJob` with non-retryable retry guard
- `DownloadManifest` v1.1 with `materialized_paths`, `exported_files`, `warnings`, and `request.filters` layout
- Support for `%d/%m/%Y` date parsing in OpenDataSUS datasource for sources like `febre_amarela`
- Developer scripts: `scripts/scaffold_opendatasus.py` and `scripts/smoke_opendatasus_sources.py`
- Contract tests for generated registry against Swagger catalog (`tests/test_opendatasus_generated_registry.py`)
- Documentation: `docs/quickstart.md`, `docs/operacao.md`, `docs/versionamento.md`

### Changed
- Project version updated to `0.5.0`
- Manifest schema version bumped from `1.0` to `1.1` (fields now optional, new layout)
- OpenDataSUS generated DEMAS sources now pass declared Swagger query parameters and substitute required path parameters
- `/sources/{source}/schema` now preserves the parameter `phase` field so the UI can group basic, export, refinement, and technical controls correctly
- UI now uses phase-based filter grouping instead of hardcoded field lists
- OpenDataSUS generated-source manifests now include `api_params` and endpoint query parameters for request traceability
- OpenDataSUS client errors now distinguish connectivity, timeout, HTTP, configuration, and response-format failures with actionable hints
- OpenDataSUS datasource failures now include CKAN/DEMAS execution context such as package resolution, endpoint, page, and resource offset when available
- OpenDataSUS export warnings are more precise about preserved artifacts, and manifests now persist warning messages for troubleshooting
- Documentation reorganized: `DOCKER_WORKFLOW.md`, `IMPROVEMENTS.md`, `INSTALL.md` moved to `docs/`
- `docs/README.md` rewritten with structured sections

### Fixed
- SINAN lazy-load guard to prevent redundant initialization

## [0.4.1] - 2026-02-24

### Added
- OpenDataSUS sources `doses_aplicadas_pni` and `zikavirus` integrated into the official pipeline through `/sources`, dynamic schema, jobs, and UI
- isolated HTTP layer for OpenDataSUS in `guaraci/opendatasus/client.py` with error handling
- OpenDataSUS datasource support with base year filters `start_year` and `end_year`, plus optional refinements `start_date`, `end_date`, and `uf`
- `keep_raw` for OpenDataSUS with default `false`
- optional OpenDataSUS export in `csv`, `parquet`, and `sqlite`

### Changed
- project version updated to `0.4.1`
- architecture, API, source, and UI documentation updated to include OpenDataSUS
- UI now separates basic filters from `Advanced Filtering`, while keeping `output_dir` in the basic block
- desktop launcher now centralizes outputs in `Guaraci Downloads` on the Desktop
- default OpenDataSUS client endpoint adjusted to DEMAS at `apidadosabertos.saude.gov.br`
- OpenDataSUS source aliases `opendatasus` and `vacinacao_covid19` removed to avoid ambiguity; canonical names must be used

## [0.4.0] - 2026-02-24

### Added
- jobs API and UI with progress monitoring through percentage, bytes, ETA, and current file
- output endpoints with `host_output_dir`, `exported_files`, `output_format`, and `export_warning`
- PySUS artifact materialization in `raw/` and local manifests
- job retry support for `failed` and `canceled`
- UI with source-schema-driven forms

### Changed
- primary SNIS flow consolidated as a `gov.br` crawler download
- legacy SNIS BigQuery integration moved to `legacy`
- alphabetical source ordering in the UI and API
- removal of the standalone `ano` filter from the jobs/UI schema for SINAN and SIH, keeping `start_year` and `end_year`
- documentation updated for the Docker-first operating model

### Fixed
- unknown parameter validation in `POST /jobs` now returns HTTP `400`
- robustness fixes in export handling and output rendering

### Notes
- local Python execution without Docker remains WIP and is not officially supported

## [0.3.0] - 2025-10-27

### Added
- DATASUS integrations for `SIM` and `SIH`
- dedicated CLIs for `sim` and `sih`
- default CSV, Parquet, and SQLite export for DATASUS sources

## [0.2.0] - 2025-10-27

### Added
- initial functional project base with Docker and modular structure
- first `SINAN` integration
- `core` layer for configuration, datasource, logging, and initial tests

## [0.1.x] - Legacy

### Notes
- initial prototype outside the current structure, without full repository history
