# API Reference

Base URL (launcher padrao): `http://localhost:8002`

## 1) Health

### `GET /health`

Retorna status da API e versao.

Exemplo:

```json
{"status":"ok","version":"0.4.1"}
```

## 2) Fontes

### `GET /sources`

Lista fontes registradas.

Retorno:

```json
[
  {"source":"doses_aplicadas_pni","title":"Doses Aplicadas PNI","mode":"opendatasus api"},
  {"source":"zikavirus","title":"Arboviroses Zikavirus","mode":"opendatasus api"},
  {"source":"sih","title":"SIH","mode":"pysus ftp"},
  {"source":"sim","title":"SIM","mode":"pysus ftp"},
  {"source":"sinan","title":"SINAN","mode":"pysus ftp"},
  {"source":"sinisa","title":"SINISA","mode":"gov.br crawl"},
  {"source":"snis","title":"SNIS","mode":"gov.br crawl"}
]
```

### `GET /sources/{source}/schema`

Retorna schema de parametros da fonte.

Observacao:
- use o nome canonico da fonte no path (`doses_aplicadas_pni`, `zikavirus`, etc.).

Campos de cada parametro:
- `name`
- `type` (`string`, `integer`, `boolean`, `string_list`)
- `description`
- `required`
- `default`
- `allowed_values`
- `minimum`
- `maximum`

## 3) Jobs

### `POST /jobs`

Cria job assincrono.

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

Respostas:
- `202`: job criado.
- `400`: parametro invalido/nao suportado.

### `GET /jobs?limit=40`

Lista jobs mais recentes.

### `GET /jobs/{job_id}`

Detalhe de um job.

Campos relevantes:
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

Solicita cancelamento.

### `POST /jobs/{job_id}/retry`

Cria novo job com mesmos parametros.

Permitido apenas para status:
- `failed`
- `canceled`

## 4) Logs e output

### `GET /jobs/{job_id}/logs?limit=120`

Retorna eventos estruturados:
- `timestamp_utc` (`YYYY-MM-DD HH:MM:SS`)
- `event`
- `level`
- `message`

### `GET /jobs/{job_id}/output`

Retorna informacoes de saida:
- `output_dir`
- `host_output_dir`
- `manifest_path`
- `output_format`
- `exported_files`
- `materialized_paths`
- `export_warning`
- `available`

### `POST /jobs/{job_id}/open-output`

Tenta abrir pasta de saida.

- Fora de Docker: chama `explorer`/`open`/`xdg-open`.
- Em Docker: retorna instrucoes para abrir no host.

## 5) Endpoints de download direto

### `POST /downloads/snis`
### `POST /downloads/sinisa`

Execucao direta sem fila.

Observacao:
- A UI atual usa majoritariamente o fluxo de jobs (`/jobs`).

## 6) Status e semantica

### Status de job

- `queued`
- `running`
- `cancel_requested`
- `completed`
- `failed`
- `canceled`

### Status de resultado (`result.status`)

- `success`
- `partial_success`
- `failed`

Regra: `result.status = failed` leva o job final para `failed`.

## 7) Exemplos de chamada

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
```

## 8) Erros comuns

- `400 Unsupported parameter(s)`:
  - parametro nao existe no schema da fonte.
- `404 Job not found`:
  - `job_id` inexistente.
- `400 Cannot retry job ... with status completed`:
  - retry so para `failed`/`canceled`.
- `OpenDataSUS returned a non-JSON response`:
  - use endpoint valido:
    - `https://apidadosabertos.saude.gov.br` (DEMAS)
    - ou `https://ckan-dadosabertos.saude.gov.br/api/3/action` (CKAN, quando disponivel)

Notas OpenDataSUS:
- `start_year` e `end_year` sao os filtros base.
- `start_date` e `end_date` sao refinamentos opcionais dentro da janela de anos.
- `keep_raw=false` (padrao) nao grava `raw/*.jsonl`; com `keep_raw=true`, grava.
