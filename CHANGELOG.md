# Changelog

## [Unreleased]

### Added
- OpenDataSUS sources `mpox`, `esavi`, `dengue`, `chikungunya`, `srag_demas`, `sindrome_gripal_leve`, and `febre_amarela` elevated to first-class epidemiological sources with start/end year enforcement and local filtering
- added support for `%d/%m/%Y` date parsing in OpenDataSUS datasource to support sources like `febre_amarela`

### Changed
- OpenDataSUS generated DEMAS sources now pass declared Swagger query parameters and substitute required path parameters
- `/sources/{source}/schema` now preserves the parameter `phase` field so the UI can group basic, export, refinement, and technical controls correctly
- OpenDataSUS generated-source manifests now include `api_params` and endpoint query parameters for request traceability
- OpenDataSUS client errors now distinguish connectivity, timeout, HTTP, configuration, and response-format failures with actionable hints
- OpenDataSUS datasource failures now include CKAN/DEMAS execution context such as package resolution, endpoint, page, and resource offset when available
- OpenDataSUS export warnings are more precise about preserved artifacts, and manifests now persist warning messages for troubleshooting

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
