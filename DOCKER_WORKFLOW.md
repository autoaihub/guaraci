# Docker Workflow

Detailed operational guide for the Guaraci Docker flow.

## 1. Build the Image

```bash
docker build -t guaraci .
```

When to use `--no-cache`:
- dependency upgrades
- inconsistent behavior after multiple changes
- suspicion of a broken Docker cache

```bash
docker build --no-cache -t guaraci .
```

## 2. Execution Modes

### 2.1 Desktop launcher (recommended)

Windows (PowerShell):

```powershell
.\scripts\desktop\start-guaraci.ps1
```

Linux or macOS (bash):

```bash
./scripts/desktop/start-guaraci.sh
```

Defaults:
- container: `guaraci-desktop`
- host port: `8002`
- internal API port: `8000`

### 2.2 Manual execution

```bash
docker run --rm -it -p 8002:8000 -v "$(pwd):/app" guaraci \
  uvicorn guaraci.api.main:app --host 0.0.0.0 --port 8000 --no-access-log
```

## 3. Launcher Internal Behavior

`start-guaraci` performs the following:
1. validates that Docker is running
2. optionally rebuilds the image
3. removes an older container with the same name
4. starts the API with volume and port mapping
5. injects variables to map container paths to host paths:
   - `GUARACI_HOST_APP_ROOT`
   - `GUARACI_CONTAINER_APP_ROOT`
6. waits for `GET /health` to return `{"status":"ok"}`

## 4. Operational Commands

Windows:

```powershell
.\scripts\desktop\launcher.ps1
.\scripts\desktop\status-guaraci.ps1
.\scripts\desktop\stop-guaraci.ps1
```

Linux or macOS:

```bash
./scripts/desktop/launcher.sh
./scripts/desktop/status-guaraci.sh
./scripts/desktop/stop-guaraci.sh
```

## 5. Data Flow with Volume Mounts

Always mount `project:/app`:

- data generated in `/app/data` inside the container is written to `./data` on the host
- job records persist in `data/jobs/download_jobs.json`

Without the mount, data is lost when the container is removed.

## 6. API and UI in Docker

Common URLs:
- UI: `http://localhost:8002/`
- Health: `http://localhost:8002/health`

Useful checks:

```bash
curl http://localhost:8002/health
curl http://localhost:8002/sources
curl http://localhost:8002/sources/sih/schema
```

## 7. Asynchronous Jobs

### Lifecycle

1. `POST /jobs`
2. monitor with `GET /jobs` and `GET /jobs/{job_id}`
3. inspect logs with `GET /jobs/{job_id}/logs`
4. inspect output with `GET /jobs/{job_id}/output`

### Job statuses

- `queued`
- `running`
- `cancel_requested`
- `completed`
- `failed`
- `canceled`

### Retry

Allowed for:
- `failed`
- `canceled`

Blocked for:
- `completed`
- `running`
- `queued`

## 8. Progress and Logs

The UI displays:
- percentage
- ETA
- current file
- transferred bytes
- structured logs

On the backend, events are persisted with compact `YYYY-MM-DD HH:MM:SS` timestamps.

## 9. Output and Folder Opening

Endpoint:
- `GET /jobs/{job_id}/output`

Returns, among other fields:
- `output_dir`
- `host_output_dir` when it can be mapped
- `exported_files`
- `output_format`
- `export_warning`

Endpoint:
- `POST /jobs/{job_id}/open-output`

Inside Docker, this usually returns instructions for manual opening on the host using `host_output_dir`.

## 10. Troubleshooting

### Port already allocated

Typical error:
- `Bind for 0.0.0.0:8002 failed: port is already allocated`

Actions:
1. change the host port
2. stop the previous container
3. validate with `docker ps`

### Older jobs fail after a restart

If the API restarts during execution, in-progress jobs can be marked as interrupted or failed.

### Too much HTTP logging in the console

Start `uvicorn` with `--no-access-log`. The launcher already does this by default.

### Export requested but no output file generated

Check `/jobs/{job_id}/output`:
- `exported_files` is empty
- `export_warning` is present

This usually means the download succeeded, but the filtered export produced no final dataset.

## 11. Development in Docker

```bash
# Tests
docker run --rm -v "$(pwd):/app" guaraci python -m pytest tests/ -v

# Interactive shell
docker run --rm -it -v "$(pwd):/app" guaraci bash
```

## 12. Note About Local Python Without Docker

The local non-Docker flow remains WIP and is not the recommended operational path.
Use Docker for final validation.
