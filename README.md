# Guaraci

| Quick Access | Resource |
| --- | --- |
| License | [MIT License](LICENSE) |
| Terms of Use | [TERMS_OF_USE.md](TERMS_OF_USE.md) |
| Citation | [CITATION.cff](CITATION.cff) |

Guaraci is a platform for downloading and orchestrating Brazilian public data sources for scientific and technical workflows. The current project scope includes:
- `SNIS` and `SINISA` (`gov.br` crawler)
- `SINAN`, `SIM`, and `SIH` (PySUS/FTP DATASUS)
- `OpenDataSUS` (`doses_aplicadas_pni` and `zikavirus`)

Current version: `0.4.1`

## Project Status

- Officially supported workflow: **Docker-first** (CLI, API, and web UI).
- Local Python execution without Docker remains **WIP** and is not the primary supported path.
- The desktop launcher centralizes downloads in `Guaraci Downloads` on the user's Desktop.

## What Works Today

- Asynchronous downloads through the API with queued jobs, cancellation, and retry.
- A desktop-oriented web UI for technical and non-technical users.
- Source-driven dynamic schemas from `/sources/{source}/schema`.
- Job progress tracking with percentage, current file, transferred bytes, ETA, and structured logs.
- On-disk job persistence in `data/jobs/download_jobs.json`.
- Optional processed dataset export in `csv`, `parquet`, or `sqlite` for PySUS and OpenDataSUS sources.

## Architecture Summary

- `guaraci/services/downloads.py`
  Handles source registration, schema-based parameter validation, and adapters for `gov.br crawl`, `pysus ftp`, and `opendatasus api`.
- `guaraci/services/jobs.py`
  Runs jobs in the background, tracks lifecycle states, supports retry and cancellation, and persists job state and logs.
- `guaraci/api/main.py`
  Exposes health, schema, jobs, logs, and output endpoints.
- `guaraci/api/static/index.html`
  Provides the web UI with schema-driven forms and job monitoring.

Detailed documentation:
- [Documentation index](docs/README.md)
- [Architecture](docs/ARCHITECTURE.md)
- [API reference](docs/API_REFERENCE.md)
- [UI guide](docs/UI_GUIDE.md)
- [Sources and filters](docs/SOURCES_AND_FILTERS.md)
- [AI handoff for OpenDataSUS](docs/AI_HANDOFF_OPENDATASUS.md)
- `AGENTS.md`

## Quick Start

### 1. Build the image

```bash
docker build -t guaraci .
```

### 2. Start the API and UI

PowerShell on Windows:

```powershell
.\scripts\desktop\start-guaraci.ps1
```

Bash on Linux or macOS:

```bash
./scripts/desktop/start-guaraci.sh
```

Default launcher URL: `http://localhost:8002/`

### 3. Check API health

```bash
curl http://localhost:8002/health
```

Expected response:

```json
{"status":"ok","version":"0.4.1"}
```

## Using the Web UI

1. Choose a source.
2. Fill in the source-specific filters generated from the schema.
3. Review the request and create the job.
4. Monitor progress and logs in the dashboard.
5. Copy the output path or open the destination folder.

Important notes:
- In Docker, opening a folder from inside the container may not work directly on the host.
- The UI exposes `host_output_dir` when host path mapping is available.
- The launcher UX points users to the `Guaraci Downloads` folder on the Desktop.

See [docs/UI_GUIDE.md](docs/UI_GUIDE.md) for the detailed UI workflow.

## Using the API

Base URL from the launcher: `http://localhost:8002`

- `GET /health`
- `GET /sources`
- `GET /sources/{source}/schema`
- `POST /jobs`
- `GET /jobs`
- `GET /jobs/{job_id}`
- `POST /jobs/{job_id}/cancel`
- `POST /jobs/{job_id}/retry`
- `GET /jobs/{job_id}/logs`
- `GET /jobs/{job_id}/output`
- `POST /jobs/{job_id}/open-output`

See [docs/API_REFERENCE.md](docs/API_REFERENCE.md) for the full API contract.

## Using the CLI

Main entry points:
- `python -m guaraci.cli.main`
- `python -m guaraci.cli.snis_cli`
- `python -m guaraci.cli.sinan_cli`
- `python -m guaraci.cli.sim_cli`
- `python -m guaraci.cli.sih_cli`

Examples:

```bash
# General help
docker run --rm -it -v "$(pwd):/app" guaraci python -m guaraci.cli.main --help

# SNIS (gov.br)
docker run --rm -it -v "$(pwd):/app" guaraci \
  python -m guaraci.cli.snis_cli download \
  --file-kinds planilhas --modules agua --extract-archives

# SINAN
docker run --rm -it -v "$(pwd):/app" guaraci \
  python -m guaraci.cli.sinan_cli download 2023 2024 --diseases RAIV --format csv

# SIM
docker run --rm -it -v "$(pwd):/app" guaraci \
  python -m guaraci.cli.sim_cli download 2023 2024 --groups CID10 --states SP RJ --format csv

# SIH
docker run --rm -it -v "$(pwd):/app" guaraci \
  python -m guaraci.cli.sih_cli download 2024 2025 --groups RJ --states RJ --months 1 --format csv
```

Note:
- In the **jobs/UI** workflow, `SIH` does not expose a standalone `year` filter.
- In the direct `sih_cli` workflow, the historical `--ano` option still exists for local export filtering.

## Sources and Filters

See the full source matrix in [docs/SOURCES_AND_FILTERS.md](docs/SOURCES_AND_FILTERS.md).

High-level summary:
- `snis` and `sinisa`
  Use `results_url`, `file_kinds`, `modules`, `extract_archives`, `overwrite`, and `timeout`.
- `doses_aplicadas_pni`
  Base API query uses `start_year` and `end_year`; optional refinement uses `uf`, `start_date`, and `end_date`; advanced controls include `keep_raw`, `batch_size`, `max_pages`, `resource_id`, and `api_base_url`.
- `zikavirus`
  Base API query uses `start_year` and `end_year`; optional refinement uses `start_date`, `end_date`, and `uf`; advanced controls include `keep_raw`, `batch_size`, `max_pages`, and `api_base_url`.
- `sinan`
  Collection uses `start_year`, `end_year`, and `diseases`; export filtering includes `output_format`, `uf`, `municipio`, `sexo`, `faixa_etaria`, `evolucao`, and `classificacao`.
- `sim`
  Collection uses `start_year`, `end_year`, `groups`, and `states`; export filtering includes `output_format`, `uf`, `municipio`, `sexo`, `causa_basica`, and `ano_obito`.
- `sih`
  Collection uses `start_year`, `end_year`, `groups`, `states`, and `months`; export filtering includes `output_format`, `uf`, `municipio`, `sexo`, and `mes`.

OpenDataSUS naming rule:
- Use canonical source names only: `doses_aplicadas_pni` and `zikavirus`.

## Output Structure

### SNIS and SINISA

```text
<output_dir>/
  raw/
  extracted/            # when extract_archives=true
  manifest.json
```

### PySUS sources

```text
<output_dir>/
  raw/                  # materialized artifacts
  <exported_files>      # when output_format is set
  manifest.json         # when artifacts were materialized
```

### OpenDataSUS sources

```text
<output_dir>/
  manifest.json
  <exported_files>      # when output_format is set
  raw/                  # only when keep_raw=true
```

`/jobs/{job_id}/output` also returns:
- `output_format`
- `exported_files`
- `export_warning`

## Desktop Launcher

Available scripts:
- Windows (`.ps1` and `.cmd`): `scripts/desktop/`
- Linux or macOS (`.sh`): `scripts/desktop/`

Useful commands on Windows:

```powershell
.\scripts\desktop\launcher.ps1
.\scripts\desktop\start-guaraci.ps1
.\scripts\desktop\status-guaraci.ps1
.\scripts\desktop\stop-guaraci.ps1
```

Useful commands on Linux or macOS:

```bash
./scripts/desktop/launcher.sh
./scripts/desktop/start-guaraci.sh
./scripts/desktop/status-guaraci.sh
./scripts/desktop/stop-guaraci.sh
```

## Development and Testing

```bash
# Full suite
docker run --rm -v "$(pwd):/app" guaraci python -m pytest tests/ -v

# Focused suite
docker run --rm -v "$(pwd):/app" guaraci python -m pytest \
  tests/test_opendatasus_swagger_catalog.py \
  tests/test_opendatasus_datasource.py \
  tests/test_services.py \
  tests/test_api.py \
  tests/test_jobs.py \
  tests/test_config.py -q
```

## Current Limitations

- Local Python execution outside Docker remains **WIP**.
- Opening folders from the UI in Docker depends on host path mapping.
- Some PySUS sources can fail due to external FTP or network instability.

## Version and Immediate Roadmap

- Current release line: `0.4.1`
- Immediate focus: expand OpenDataSUS datasets and strengthen retries and observability per source.

## Additional Documentation

- `INSTALL.md`
- `DOCKER_WORKFLOW.md`
- `CONTRIBUTING.md`
- `IMPROVEMENTS.md`
- `CHANGELOG.md`

## License

Guaraci is distributed under the MIT License. See [LICENSE](LICENSE) for the full text.

## Terms of Use

Use of Guaraci requires compliance with the terms, policies, and legal constraints of each upstream data source. See [TERMS_OF_USE.md](TERMS_OF_USE.md) for the full project terms, including warranty disclaimers and user responsibilities.

## Citation

If you use Guaraci in research, technical reports, or derived software, cite the software version that supported your work. Formal citation metadata is available in [CITATION.cff](CITATION.cff).

Recommended software citation for the current release:

```text
Vogel Lopes, Luis Felipe, dos Reis Teixeira, Pedro Guilherme, Bonidia, Robson Parmezan, and de Carvalho, André Carlos Ponce de Leon Ferreira. 2026. Guaraci (Version 0.4.1) [Computer software]. https://github.com/autoaihub/guaraci
```
