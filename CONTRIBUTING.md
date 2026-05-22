# Contributing to Guaraci

Practical guide for technical contributions.

## Main Environment Rule

- Development and validation must be done in **Docker**.
- Local execution without Docker remains **WIP** and should not be treated as the approval baseline.

## Quick Setup

```bash
git clone https://github.com/autoaihub/guaraci.git
cd guaraci
docker build -t guaraci .
```

## Recommended Development Flow

1. Create a working branch.
2. Implement a small, isolated change.
3. Run the relevant tests in the container.
4. Update the impacted documentation.
5. Open a PR with a concise description and the commands used for validation.

## Current Structure at a High Level

- `guaraci/core/`: contracts, configuration, result types, and datasource base classes
- `guaraci/snis/`: crawler sources (`snis`, `sinisa`) and legacy BigQuery code in `legacy/`
- `guaraci/datasus/`: PySUS sources (`sinan`, `sim`, `sih`)
- `guaraci/services/`: download orchestration and asynchronous jobs
- `guaraci/services/opendatasus_registry.py`: generated OpenDataSUS DEMAS source registry
- `scripts/scaffold_opendatasus.py`: helper for regenerating OpenDataSUS source blocks from the local Swagger catalog
- `guaraci/api/`: FastAPI and static web UI
- `guaraci/cli/`: per-source CLIs

## Code Standards

- Python 3.11+
- Formatting: `black`
- Imports: `isort`
- Typing: `mypy`
- Tests: `pytest`

Commands:

```bash
# Tests
docker run --rm -v "$(pwd):/app" guaraci python -m pytest tests/ -v

# Formatting
docker run --rm -v "$(pwd):/app" guaraci python -m black guaraci/ tests/
docker run --rm -v "$(pwd):/app" guaraci python -m isort guaraci/ tests/

# Typing
docker run --rm -v "$(pwd):/app" guaraci python -m mypy guaraci/
```

## Conventions

- Modules and functions: `snake_case`
- Classes: `CamelCase`
- Constants: `UPPER_SNAKE_CASE`
- Public API names should stay in English
- User-facing messages and logs may remain in Portuguese when the product requires it

## Test Scope by Area

### If you changed API, UI, or jobs

Run at least:

```bash
docker run --rm -v "$(pwd):/app" guaraci python -m pytest tests/test_api.py tests/test_jobs.py -v
```

### If you changed source schemas or validation

```bash
docker run --rm -v "$(pwd):/app" guaraci python -m pytest tests/test_services.py -v
```

### If you changed a specific datasource

Run the datasource-specific tests and related coverage.

### If you changed OpenDataSUS generated sources

```bash
docker run --rm -v "$(pwd):/app" guaraci python -m pytest \
  tests/test_opendatasus_swagger_catalog.py \
  tests/test_opendatasus_generated_registry.py \
  tests/test_opendatasus_datasource.py \
  tests/test_services.py \
  tests/test_api.py -q
```

For a low-volume live smoke check against the official DEMAS API:

```bash
docker run --rm -v "$(pwd):/app" guaraci python scripts/smoke_opendatasus_sources.py --allow-failures
```

Path-based endpoints require representative IDs. Provide them with `--samples` when available.

## Documentation Rules

Always update docs when a change affects:
- source parameters
- export behavior
- job states
- API endpoints
- UI behavior or UX

Main files:
- `README.md`
- `CHANGELOG.md`
- `AGENTS.md`
- `docs/quickstart.md`
- `docs/ARCHITECTURE.md`
- `docs/API_REFERENCE.md`
- `docs/UI_GUIDE.md`
- `docs/SOURCES_AND_FILTERS.md`
- `docs/AI_HANDOFF_OPENDATASUS.md`

## Pull Requests

Include in the PR:
- context and problem statement
- what changed
- risks and trade-offs
- test commands executed
- documentation impact

Functional changes without documentation updates should be treated as incomplete.
