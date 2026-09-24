# API Reference

Default launcher base URL: `http://localhost:8002`

## 1. Health

### `GET /health`

Returns API status and version.

Example:

```json
{"status":"ok","version":"0.6.0"}
```

## 2. Sources

### `GET /sources`

Lists the registered sources.

The response includes the manually curated sources and the OpenDataSUS DEMAS sources generated from the local Swagger catalog.

Query parameters:
- `theme` (optional): restricts the listing to one theme slug. An unknown slug
  returns `400`, not an empty list. See `GET /themes`.

Response:

```json
[
  {"source":"doses_aplicadas_pni","title":"Doses Aplicadas PNI","mode":"opendatasus api","themes":["imunizacao"]},
  {"source":"zikavirus","title":"Arboviroses Zikavirus","mode":"opendatasus api","themes":["vigilancia_epidemiologica"]},
  {"source":"sih","title":"SIH","mode":"datasus ftp","themes":["assistencia_hospitalar","oncologia"]},
  {"source":"sim","title":"SIM","mode":"datasus ftp","themes":["mortalidade","oncologia"]},
  {"source":"sinan","title":"SINAN","mode":"datasus ftp","themes":["vigilancia_epidemiologica"]},
  {"source":"sinisa","title":"SINISA","mode":"gov.br crawl","themes":["saneamento"]},
  {"source":"snis","title":"SNIS","mode":"gov.br crawl","themes":["saneamento"]}
]
```

A source may carry more than one theme. That is intentional: `sim` answers both
`mortalidade` and `oncologia`, because mortality by neoplasm is reached through
it. A theme means "there is data on this subject here", not "this source is
only about this".

### `GET /sources/{source}/schema`

Returns the parameter schema for the selected source.

Note:
- Use the canonical source name in the path (`doses_aplicadas_pni`, `zikavirus`, and so on).

Parameter fields:
- `name`
- `type` (`string`, `integer`, `boolean`, `string_list`)
- `description`
- `phase` (`basico`, `coleta`, `refinamento`, `exportacao`, or `tecnica`)
- `required`
- `default`
- `allowed_values`
- `minimum`
- `maximum`

### `GET /themes`

Returns the controlled theme vocabulary used to navigate the catalogue, with
the number of registered sources under each theme.

```json
[
  {"slug":"oncologia","label":"Oncologia","description":"Rastreamento, diagnóstico, tratamento e mortalidade por câncer.","source_count":5}
]
```

### `GET /presets`

Lists the ready-made thematic cuts. A theme answers "where is the data on this
subject?"; a preset answers the next question, "with which parameters do I pull
it?", across several sources at once.

### `GET /presets/{name}`

Returns one preset. Reading it validates every step's parameters against the
live schema of the corresponding source, so a recipe that has gone stale fails
here instead of failing midway through a long download. Unknown name returns
`404`.

```json
{
  "name": "oncologia",
  "title": "Oncologia (rastreamento, tratamento, internação e óbito)",
  "themes": ["oncologia"],
  "steps": [
    {"source":"siscan","params":{"groups":["CC","CM"]},"rationale":"...","refine":null},
    {"source":"sia","params":{"groups":["AQ","AR"]},"rationale":"...","refine":null},
    {"source":"sim","params":{},"rationale":"...","refine":"O SIM vem completo. Filtre a causa básica (CAUSABAS) por CID-10 C00-C97..."}
  ],
  "caveats": ["Não há dado de INCIDÊNCIA neste preset. ..."]
}
```

Two fields carry the honesty of the preset and should not be ignored by a
client:

- `refine`: `null` means the step's `params` already deliver the full cut.
  Filled means the download brings the whole base and the final cut depends on
  a post-collection filter, described there. The DATASUS FTP does not filter by
  CID at the origin, so `sih` and `sim` always arrive whole.
- `caveats`: known limitations of the cut, including data that is *absent*. The
  `oncologia` preset has no incidence data, because Brazilian cancer incidence
  comes from the INCA population-based registries (RCBP), published only as
  reports and a tabulator, with no automatable path that satisfies the
  project's primary-source rule.

### `POST /sources/{source}/discovery`

Runs source discovery without downloading files. Currently supported for `sih`.

Body:

```json
{
  "params": {
    "start_year": 2019,
    "end_year": 2019,
    "groups": ["RD"],
    "states": ["AC"],
    "months": ["1"]
  }
}
```

Response fields include `documents_found`, `total_size_bytes`, `by_group`,
`by_state`, and a small `sample` list. Use this before creating broad SIH jobs.

## 3. Jobs

### `POST /jobs`

Creates an asynchronous job.

Body:

```json
{
  "source": "snis",
  "params": {
    "file_kinds": ["planilhas"],
    "modules": ["agua"],
    "extract_archives": true
  }
}
```

Responses:
- `202`: job created
- `400`: invalid or unsupported parameter

### `GET /jobs?limit=40`

Lists the most recent jobs.

### `GET /jobs/{job_id}`

Returns job details.

Relevant fields:
- `status`
- `progress`
- `attempt`
- `retry_of`
- `files_total`
- `files_completed`
- `bytes_downloaded`
- `bytes_total`
- `elapsed_seconds`
- `eta_seconds`
- `current_file`
- `result`
- `error`

### `POST /jobs/{job_id}/cancel`

Requests cancellation.

### `POST /jobs/{job_id}/retry`

Creates a new job with the same parameters.

Allowed only when the current job status is:
- `failed`
- `canceled`

## 4. Logs and Output

### `GET /jobs/{job_id}/logs?limit=120`

Returns structured events:
- `timestamp_utc` (`YYYY-MM-DD HH:MM:SS`)
- `event`
- `level`
- `message`

### `GET /jobs/{job_id}/output`

Returns output metadata:
- `output_dir`
- `host_output_dir`
- `manifest_path`
- `output_format`
- `exported_files`
- `materialized_paths`
- `export_warning`
- `available`

### `POST /jobs/{job_id}/open-output`

Attempts to open the output folder.

- Outside Docker: calls `explorer`, `open`, or `xdg-open`.
- Inside Docker: returns instructions for opening the folder on the host.

## 5. Direct Download Endpoints

### `POST /downloads/snis`
### `POST /downloads/sinisa`

Runs a direct download without the jobs queue.

Note:
- The current UI primarily uses the jobs flow (`/jobs`).

## 6. Status Semantics

### Job status

- `queued`
- `running`
- `cancel_requested`
- `completed`
- `failed`
- `canceled`

### Result status (`result.status`)

- `success`
- `partial_success`
- `failed`

Rule: `result.status = failed` makes the final job status `failed`.

## 7. Request Examples

### PowerShell

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8002/sources/sinan/schema"

$body = @{
  source = "sinan"
  params = @{
    start_year = 2023
    end_year = 2024
    diseases = @("RAIV")
    output_format = "csv"
  }
} | ConvertTo-Json -Depth 8

$job = Invoke-RestMethod -Method Post -Uri "http://localhost:8002/jobs" -ContentType "application/json" -Body $body
Invoke-RestMethod -Method Get -Uri "http://localhost:8002/jobs/$($job.job_id)"
Invoke-RestMethod -Method Get -Uri "http://localhost:8002/jobs/$($job.job_id)/output"
```

### curl

```bash
curl http://localhost:8002/sources/sinan/schema

curl -X POST http://localhost:8002/jobs \
  -H "Content-Type: application/json" \
  -d '{"source":"sinan","params":{"start_year":2023,"end_year":2024,"diseases":["RAIV"],"output_format":"csv"}}'

curl -X POST http://localhost:8002/jobs \
  -H "Content-Type: application/json" \
  -d '{"source":"doses_aplicadas_pni","params":{"start_year":2025,"end_year":2025,"uf":"SP","output_format":"csv","keep_raw":false}}'

curl -X POST http://localhost:8002/jobs \
  -H "Content-Type: application/json" \
  -d '{"source":"cnes_estabelecimentos","params":{"codigo_uf":"35","status":"ATIVO","output_format":"csv"}}'
```

## 8. Common Errors

- `400 Unsupported parameter(s)`:
  - the parameter does not exist in the source schema
- `404 Job not found`:
  - the `job_id` does not exist
- `400 Cannot retry job ... with status completed`:
  - retry is available only for `failed` or `canceled`
- `Could not connect to OpenDataSUS endpoint ...`:
  - check DNS, proxy/firewall rules, and upstream availability
  - retry may succeed when the endpoint is temporarily unstable
- `OpenDataSUS request failed (429|5xx)`:
  - retry later or reduce the query window / request volume
- `OpenDataSUS request failed (404)`:
  - confirm `api_base_url`, `resource_id`, dataset path, and CKAN vs DEMAS mode
- `OpenDataSUS returned a non-JSON response`:
  - use a valid endpoint:
    - `https://apidadosabertos.saude.gov.br` (DEMAS)
    - `https://ckan-dadosabertos.saude.gov.br/api/3/action` (CKAN, when available)

OpenDataSUS notes:
- `start_year` and `end_year` are the base filters.
- `start_date` and `end_date` are optional refinements inside the selected year window.
- Auto-generated DEMAS sources expose native Swagger parameters as source-specific schema fields.
- DEMAS path parameters such as `codigo_cnes` are required when the endpoint path contains `{codigo_cnes}`.
- `keep_raw=false` by default does not write `raw/*.jsonl`; `keep_raw=true` does.
- `export_warning` may include truncation (`max_pages`) or export-preservation guidance.


---
? [Índice da documentação](README.md) · [Voltar ao projeto](../README.md)
