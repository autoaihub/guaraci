# UI Guide

Desktop web panel at `http://localhost:8002/` in the default launcher flow.

## 1. Interface Goal

The UI allows users to create and monitor downloads without depending on the CLI.

The interface covers:
- source selection
- dynamic schema-based filters
- job creation
- progress monitoring
- log inspection
- output path access
- cancellation and retry

## 2. Layout

The UI is organized into two main areas:

1. **New Job** with a three-step wizard
   - `1. Source`
   - `2. Filters`
   - `3. Review`
2. **Monitoring**
   - selected job summary
   - progress bar
   - output panel
   - logs
   - jobs table

## 3. Creating a Job

### Step 1. Source

- Select a source in the dropdown.
- The UI calls `GET /sources/{source}/schema`.
- It displays the source mode such as `gov.br crawl` or `pysus ftp`.

### Step 2. Filters

- Fields are generated dynamically from the schema.
- `Download Directory` remains in the basic block and appears before `output_format`.
- Technical parameters and local refinements are grouped under the expandable `Advanced Filtering` block.
- Field types:
  - `integer` -> numeric input
  - `boolean` -> checkbox
  - `string` with `allowed_values` -> select
  - `string_list` with `allowed_values` -> multi-select
  - everything else -> text input
- The `?` icon shows contextual help text.

### Step 3. Review

- Shows the chosen source, mode, and parameters.
- Confirmation sends `POST /jobs`.

## 4. Real-Time Monitoring

On each refresh cycle, the UI queries:
- `GET /jobs?limit=40`
- `GET /jobs/{job_id}`
- `GET /jobs/{job_id}/logs?limit=120`
- `GET /jobs/{job_id}/output`

Displayed indicators:
- status and percentage
- attempt number
- completed files versus total files
- transferred bytes
- elapsed time and ETA
- current file

## 5. Jobs Table

Row actions:
- `Select`
- `Cancel`
- `Retry`

Rules:
- `Cancel` is enabled only for non-terminal jobs.
- `Retry` is enabled only for `failed` and `canceled`.

## 6. Output and Traceability

The output panel shows:
- output folder
- export format when applicable
- number and list of exported files
- `export_warning` when no export file was generated

Buttons:
- `Copy Path`
- `Open Folder`

Docker note:
- inside a container, `Open Folder` may return instructions instead of opening the folder directly
- use `host_output_dir` when the host mapping is available

## 7. Logs

Format:
- `[YYYY-MM-DD HH:MM:SS] [LEVEL] message`

The UI log stream reflects job pipeline events, not only HTTP server logs.

## 8. Source-Specific Tips

### 8.1 SNIS and SINISA

- Start with `file_kinds = planilhas`.
- Use `modules` to reduce volume.
- Set `extract_archives = true` to unzip archives automatically.

### 8.2 OpenDataSUS

- Available sources: `doses_aplicadas_pni` and `zikavirus`.
- Start with the native API filters `start_year` and `end_year`.
- Set `output_format` if you need exported files.
- `Advanced Filtering` contains local refinements and technical options such as:
  - `start_date`
  - `end_date`
  - `keep_raw`
  - `api_base_url`
  - `batch_size`
  - `max_pages`
  - `resource_id`
- For `zikavirus`, `uf` is treated as a local refinement and stays in the advanced block.
- If the API returns HTML instead of JSON, switch `api_base_url` to a valid endpoint:
  - `https://apidadosabertos.saude.gov.br` (DEMAS)
  - `https://ckan-dadosabertos.saude.gov.br/api/3/action` (CKAN, when available)
- When an OpenDataSUS job fails, the job error text should now indicate whether the issue was connectivity, HTTP status, configuration, or unexpected response format.

### 8.3 SINAN, SIM, and SIH

- Define the period first with `start_year` and `end_year`.
- Use diseases, groups, and state filters to reduce cardinality.
- Set `output_format` only when you need a final export file.

## 9. Common Problems

### A job stays in `running` for too long

- The cause may be slow network or FTP responses.
- Check the job logs to confirm whether progress is still moving.

### The download finished but no CSV was generated

- Confirm that `output_format` was included in the payload.
- Check `export_warning` in the job output; it now indicates whether only the manifest was preserved or whether `keep_raw=true` is recommended for reprocessing.
- Check `exported_files` and `export_warning` in the output panel.

### Port 8002 is unavailable

- Start the launcher on a different port.

### The UI does not load sources

- Check `GET /health` and `GET /sources`.
- Verify that the API and container are running.
