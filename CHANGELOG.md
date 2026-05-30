# Changelog

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

### DATASUS: direct-FTP backend (PLANO_DATASUS_FTP_DIRETO phases 1-4)
- Added a direct DATASUS FTP layer under `guaraci/datasus/ftp/` (`client`, `catalog`, `discovery`, `dbc`, shared `orchestration`, and per-source `sih_backend`/`sim_backend`/`sinan_backend`) built on stdlib `ftplib` + `pyreaddbc`/`dbfread`, replacing the ~20 transitive dependencies of `pysus[dbc]` with 2 packages while keeping the same primary source (`ftp.datasus.gov.br`).
- SIH, SIM, and SINAN now select their backend via `GUARACI_DATASUS_BACKEND={ftp|pysus}`, resolved by the shared dependency-free selector `guaraci/datasus/backend.py`.
- **Default backend flipped to `ftp`** (phase 4): the `datasus` extra now installs only `pyreaddbc` + `dbfread`. The legacy PySUS path stays installable for one release via the new `datasus-legacy` extra and selectable via `GUARACI_DATASUS_BACKEND=pysus`. This supersedes the earlier same-version note above about requiring `pysus[dbc]` in Docker builds.
- Bumped the PySUS pin to `pysus>=2.2.0` (the obsolete `[dbc]` extra was folded into the base package upstream and now warns on `uv lock`).
- API/CLI/UI contracts unchanged: the `mode` descriptor for SIH/SIM/SINAN remains `pysus ftp` and the parquet output schema is identical.

### Estado (direct-FTP migration)
- Tests: full suite 319 passed, 3 skipped (opt-in live FTP smoke + Docker-specific). The two failures in `tests/test_sinan_datasource.py` (`test_sinan_download_uses_single_worker`, `test_download_file_safe_closes_ftp_singleton`) are pre-existing — they reference `ThreadPoolExecutor`/`_download_file_safe`, already absent from `sinan.py` before this branch — and are unrelated to this migration; flagged for separate cleanup.
- Gates pendentes: bit-exact parity vs PySUS and 1 week of opt-in production validation were NOT met before the default flip; the flip was authorized anyway and is reversible via a single env var (`GUARACI_DATASUS_BACKEND=pysus`) or by reverting `DEFAULT_BACKEND` in `guaraci/datasus/backend.py`.

### DATASUS: 11 more systems via direct FTP (PLANO_DATASUS_FTP_DIRETO phase 5)
- Extended the direct-FTP integration beyond SIH/SIM/SINAN to eleven more DATASUS microdata systems: `sinasc`, `sia` (SIA-SUS ambulatorial), `cnes`, `pni` (historical SI-PNI), `ciha`, `cih`, `siscan`, `sisprenatal`, `resp`, `pce`, and `painel_oncologia`. All FTP-only (no PySUS legacy path).
- New spec-driven engine: `guaraci/datasus/ftp/specs.py` (one `SystemSpec` per system — filename regex + FTP paths + dimension flags), a generic `discover_spec`, plain-`.DBF` decoding in `dbc.py` (PNI ships uncompressed DBF), and `generic_backend`. Paths and group sets (SIA's 14 groups, CNES's 13, PNI's CPNI/DPNI) were confirmed by live FTP recon, not guessed.
- One generic `FtpDataSource` (parametrised by spec) plus registration of all eleven as platform sources (`mode = "datasus ftp"`), reachable via `/sources`, `/sources/{source}/schema`, `/jobs`, the UI, and a new generic `guaraci datasus` CLI (`list` + `download`).
- Tests: 56 new offline tests (specs, discovery layouts, DBF decode, generic backend, datasource, registry, CLI). A live discovery smoke validated all eleven specs against the server. Full suite green except the 2 pre-existing stale `tests/test_sinan_datasource.py` failures.
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
