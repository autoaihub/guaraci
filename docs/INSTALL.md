# Installation Guide

This project should be treated as **Docker-first**.

## Support Status

- Officially supported: Docker-based execution for CLI, API, and UI.
- Not officially supported: local Python execution without Docker, which remains WIP.

## Prerequisites

- Docker Desktop on Windows or macOS, or Docker Engine on Linux
- Git

## Quick Installation

```bash
git clone https://github.com/autoaihub/guaraci.git
cd guaraci
docker build -t guaraci .
```

## Basic Verification

```bash
# Version
docker run --rm guaraci python -c "import guaraci; print(guaraci.__version__)"

# Package installation smoke test
docker run --rm guaraci python -m pytest tests/test_install.py -v
```

## Recommended Operation: Desktop Launcher

### Windows (PowerShell)

```powershell
.\scripts\desktop\start-guaraci.ps1
```

The UI opens at `http://localhost:8002/`.

Other commands:

```powershell
.\scripts\desktop\launcher.ps1
.\scripts\desktop\status-guaraci.ps1
.\scripts\desktop\stop-guaraci.ps1
```

`.cmd` shortcuts for double-click use:
- `scripts\desktop\launcher.cmd`
- `scripts\desktop\start-guaraci.cmd`
- `scripts\desktop\status-guaraci.cmd`
- `scripts\desktop\stop-guaraci.cmd`

### Linux or macOS (bash)

```bash
./scripts/desktop/start-guaraci.sh
```

Other commands:

```bash
./scripts/desktop/launcher.sh
./scripts/desktop/status-guaraci.sh
./scripts/desktop/stop-guaraci.sh
```

## Manual Operation Without the Launcher

### Start the API on a custom port

PowerShell:

```powershell
docker run --rm -it -p 8002:8000 -v "${PWD}:/app" guaraci \
  uvicorn guaraci.api.main:app --host 0.0.0.0 --port 8000 --no-access-log
```

Bash:

```bash
docker run --rm -it -p 8002:8000 -v "$(pwd):/app" guaraci \
  uvicorn guaraci.api.main:app --host 0.0.0.0 --port 8000 --no-access-log
```

## Running Tests in the Container

```bash
# Full suite
docker run --rm -v "$(pwd):/app" guaraci python -m pytest tests/ -v

# API and jobs
docker run --rm -v "$(pwd):/app" guaraci python -m pytest tests/test_api.py tests/test_jobs.py -v
```

## Data Strategy and Volume Mounts

Always mount the project to `/app` to persist outputs on the host:

- Windows PowerShell: `-v "${PWD}:/app"`
- Linux or macOS: `-v "$(pwd):/app"`

Without a volume mount, data remains inside the ephemeral container.

## Quick Troubleshooting

### Port already in use

Common error: `Bind for 0.0.0.0:8002 failed: port is already allocated`

Actions:
1. Change the host port, for example `-p 8003:8000`.
2. Stop the running container with `scripts/desktop/stop-guaraci.*`.

### API is up but the UI has no data

Check:
- `GET /health`
- `GET /sources`
- write permissions for `data/`

### "Open Folder" button in Docker

Inside a container, opening a folder on the host is not direct. Use the `host_output_dir` value shown by the UI or API.

## Local Python Execution Without Docker (WIP)

This path exists only for occasional development and may fail.

Current limits:
- inconsistent behavior across systems
- higher risk of dependency conflicts, especially in the PySUS and FTP stack
- not validated for end users

If you need to test locally, do so at your own risk and validate the final behavior in Docker before treating the result as definitive.
