# Sources and Filters

Reference document for the parameters exposed through the schema, API, and UI.

## 1. Execution Phases

For PySUS sources, parameters can act in different phases:

- **Collection/download**: which source files to fetch
- **Export/filtering**: how to filter the final dataset before export

The UI shows these parameters in one flow, but they still represent different stages.

## 2. Supported Sources

All sources are integrated directly from the official primary publisher
(see principle 20 in the `vogel-stack`). Curated third-party mirrors
(Base dos Dados, microdatasus, PCDaS) are not used as sources even when
they expose more convenient query layers.

- `snis` (`gov.br crawl`) — primary: `app4.mdr.gov.br/serieHistorica/`
- `sinisa` (`gov.br crawl`) — primary: gov.br SINISA pages
- `doses_aplicadas_pni` (`opendatasus api`) — primary: `opendatasus.saude.gov.br`
- `zikavirus` (`opendatasus api`) — same
- `febre_amarela` (`opendatasus api`) — same
- `mpox` (`opendatasus api`) — same
- `esavi` (`opendatasus api`) — same
- `dengue` (`opendatasus api`) — same
- `chikungunya` (`opendatasus api`) — same
- `srag_demas` (`opendatasus api`) — same
- `sindrome_gripal_leve` (`opendatasus api`) — same
- OpenDataSUS DEMAS sources generated from `guaraci/opendatasus/utils/swagger.json`
- `sinan` (`pysus ftp`) — primary: `ftp.datasus.gov.br/dissemin/publicos/SINAN/`
- `sim` (`pysus ftp`) — primary: `ftp.datasus.gov.br/dissemin/publicos/SIM/`
- `sih` (`pysus ftp`) — primary: `ftp.datasus.gov.br/dissemin/publicos/SIHSUS/`
- `sinasc` (`datasus ftp`) — primary: `ftp.datasus.gov.br/dissemin/publicos/SINASC/`
- `sia` (`datasus ftp`) — primary: `ftp.datasus.gov.br/dissemin/publicos/SIASUS/`
- `cnes` (`datasus ftp`) — primary: `ftp.datasus.gov.br/dissemin/publicos/CNES/`
- `pni` (`datasus ftp`) — primary: `ftp.datasus.gov.br/dissemin/publicos/PNI/` (histórico SI-PNI; `.DBF`)
- `ciha` (`datasus ftp`) — primary: `ftp.datasus.gov.br/dissemin/publicos/CIHA/`
- `cih` (`datasus ftp`) — primary: `ftp.datasus.gov.br/dissemin/publicos/CIH/` (legado 2008–2010)
- `siscan` (`datasus ftp`) — primary: `ftp.datasus.gov.br/dissemin/publicos/SISCAN/`
- `sisprenatal` (`datasus ftp`) — primary: `ftp.datasus.gov.br/dissemin/publicos/SISPRENATAL/`
- `resp` (`datasus ftp`) — primary: `ftp.datasus.gov.br/dissemin/publicos/RESP/`
- `pce` (`datasus ftp`) — primary: `ftp.datasus.gov.br/dissemin/publicos/PCE/`
- `painel_oncologia` (`datasus ftp`) — primary: `ftp.datasus.gov.br/dissemin/publicos/painel_oncologia/`
- The eleven `datasus ftp` systems above connect directly via stdlib `ftplib` (phase 5 of the direct-FTP migration). Collection params: `start_year`/`end_year`, plus `groups` for multi-group systems (SIA, CNES, SISCAN, PNI) and `states` for state-level systems. `CMD` and `ANS` are intentionally not integrated.
- All eleven support discovery preflight (`POST /sources/{source}/discovery` or `guaraci datasus discover <source> <start> <end>`): it returns the file count broken down by group/UF without downloading — recommended before pulling large systems like SIA. File sizes are omitted by default to keep the preflight fast.
- `nasa_power` (`nasa power api`) — primary: `power.larc.nasa.gov` (NASA POWER,
  global meteorological/solar series; no third-party mirror involved)
- `nasa_firms` (`nasa firms api`) — primary: `firms.modaps.eosdis.nasa.gov`
  (NASA FIRMS active-fire detections; requires a free MAP_KEY)
- `nasa_gpm` (`nasa gpm api`) — primary: `gpm1.gesdisc.eosdis.nasa.gov`
  (NASA GPM IMERG daily precipitation via GES DISC OPeNDAP; requires an
  Earthdata token; experimental)

Convention:
- Always use the canonical `source` value returned by `GET /sources`.
- The `mode` field on `GET /sources` describes the transport, not the
  publisher. `pysus ftp` means "DATASUS FTP, fetched through PySUS"; the
  fetch layer may change without
  altering the source identity.

## 3. Parameters by Source

### 3.1 SNIS (`snis`)

| Parameter | Type | Phase | Notes |
| --- | --- | --- | --- |
| `output_dir` | string | download | Output folder, defaulting to `Guaraci Downloads` on the Desktop |
| `results_url` | string | download | Custom base page URL |
| `file_kinds` | string_list | download | `planilhas`, `relatorios`, `glossarios`, `atestados`, `all` |
| `modules` | string_list | download | `gestao_municipal`, `agua`, `esgoto`, `residuos`, `aguas_pluviais` |
| `extract_archives` | boolean | download | Extract zip archives |
| `overwrite` | boolean | download | Overwrite existing files |
| `timeout` | integer | download | HTTP timeout |

### 3.2 SINISA (`sinisa`)

Uses the same base schema as SNIS.

### 3.3 OpenDataSUS (`doses_aplicadas_pni`)

| Parameter | Type | Phase | Notes |
| --- | --- | --- | --- |
| `output_dir` | string | download | Output folder, defaulting to `Guaraci Downloads` on the Desktop |
| `output_format` | string | export | `csv`, `parquet`, `sqlite` |
| `start_year` | integer | download | Initial query year, used as a base API filter |
| `end_year` | integer | download | Final query year, used as a base API filter |
| `uf` | string | download/refinement | Optional state code such as `SP` |
| `start_date` | string | local refinement | Optional initial date (`YYYY-MM-DD`) inside the selected year window |
| `end_date` | string | local refinement | Optional final date (`YYYY-MM-DD`) inside the selected year window |
| `keep_raw` | boolean | download | Save `raw/*.jsonl`, default `false` |
| `batch_size` | integer | download | API pagination size |
| `max_pages` | integer | download | Per-year page limit for controlling volume and runtime |
| `resource_id` | string | download | Optional CKAN resource override |
| `api_base_url` | string | download | Optional API base override |

### 3.4 OpenDataSUS Epidemiological Sources (`zikavirus`, `febre_amarela`, `mpox`, `esavi`, `dengue`, `chikungunya`, `srag_demas`, `sindrome_gripal_leve`)

| Parameter | Type | Phase | Notes |
| --- | --- | --- | --- |
| `output_dir` | string | download | Output folder, defaulting to `Guaraci Downloads` on the Desktop |
| `output_format` | string | export | `csv`, `parquet`, `sqlite` |
| `start_year` | integer | download | Initial query year, used as a base API filter |
| `end_year` | integer | download | Final query year, used as a base API filter |
| `start_date` | string | local refinement | Optional initial date (`YYYY-MM-DD`) inside the selected year window |
| `end_date` | string | local refinement | Optional final date (`YYYY-MM-DD`) inside the selected year window |
| `uf` | string | local refinement | Optional state code such as `SP` |
| `keep_raw` | boolean | download | Save `raw/*.jsonl`, default `false` |
| `batch_size` | integer | download | API pagination size |
| `max_pages` | integer | download | Page limit for controlling volume and runtime |
| `api_base_url` | string | download | Optional API base override |

OpenDataSUS notes:
- The current UX rule is to prioritize native API filters in the basic form.
- Local refinements and technical options belong in the advanced UI block.
- `max_pages` may generate an `export_warning` if the query was truncated before exhausting remote pages.
- If export fails with `keep_raw=false`, the warning advises re-running with `keep_raw=true` to preserve a raw snapshot.

### 3.5 Auto-generated OpenDataSUS DEMAS sources

These sources are generated from the local DEMAS Swagger catalog.

Examples:
- `cnes_estabelecimentos`
- `cnes_estabelecimentos_{codigo_cnes}`
- `sisagua_vigilancia_parametros_basicos`
- `sindrome_gripal_leve`
- `srag_demas`

Common standardized parameters:

| Parameter | Type | Phase | Notes |
| --- | --- | --- | --- |
| `output_dir` | string | tecnica | Output folder, defaulting to `Guaraci Downloads` on the Desktop |
| `output_format` | string | exportacao | `csv`, `parquet`, `sqlite` |
| `keep_raw` | boolean | tecnica | Save `raw/*.jsonl`, default `false` |
| `batch_size` | integer | tecnica | DEMAS pagination size |
| `max_pages` | integer | tecnica | Page limit for controlling volume and runtime |
| `api_base_url` | string | tecnica | Optional DEMAS base URL override |

Source-specific parameters:
- Native Swagger query parameters are exposed as `basico` fields and passed to DEMAS as query parameters.
- Native Swagger path parameters are exposed as required `basico` fields and substituted into paths such as `/cnes/estabelecimentos/{codigo_cnes}`.
- `limit` and `offset` are not exposed to users; Guaraci controls them through `batch_size` and pagination.
- Unknown parameters are rejected by the standard schema validation path.
- Contract tests verify every generated source against the local Swagger catalog; live upstream availability can be checked with `scripts/smoke_opendatasus_sources.py`.

### 3.6 SINAN (`sinan`)

| Parameter | Type | Phase | Notes |
| --- | --- | --- | --- |
| `output_dir` | string | download | Output folder |
| `output_format` | string | export | `csv`, `parquet`, `sqlite` |
| `start_year` | integer | download | Initial year |
| `end_year` | integer | download | Final year |
| `diseases` | string_list | download | Supported disease list |
| `uf` | string | export | Filter by state |
| `municipio` | string | export | Text filter |
| `sexo` | string | export | `M` or `F` |
| `faixa_etaria` | string | export | Age range code |
| `evolucao` | string | export | Outcome filter |
| `classificacao` | string | export | Classification filter |

Notes:
- The standalone `ano` field was removed from the jobs/UI schema.
- The jobs/UI temporal window is defined by `start_year` and `end_year`.

### 3.7 SIM (`sim`)

| Parameter | Type | Phase | Notes |
| --- | --- | --- | --- |
| `output_dir` | string | download | Output folder |
| `output_format` | string | export | `csv`, `parquet`, `sqlite` |
| `start_year` | integer | download | Initial year |
| `end_year` | integer | download | Final year |
| `groups` | string_list | download | SIM groups |
| `states` | string_list | download | Collection states |
| `uf` | string | export | State filter in the final dataset |
| `municipio` | string | export | Text filter |
| `sexo` | string | export | `M` or `F` |
| `causa_basica` | string | export | Basic cause of death |
| `ano_obito` | integer | export | Year of death |

### 3.8 SIH (`sih`)

| Parameter | Type | Phase | Notes |
| --- | --- | --- | --- |
| `output_dir` | string | download | Output folder |
| `output_format` | string | export | `csv`, `parquet`, `sqlite` |
| `start_year` | integer | download | Initial year |
| `end_year` | integer | download | Final year |
| `groups` | string_list | download | SIH groups; leave empty to include all groups |
| `states` | string_list | download | Collection states |
| `months` | string_list | download | Collection months (`1-12`); leave empty to include all months |
| `uf` | string | export | State filter in the final dataset |
| `municipio` | string | export | Text filter |
| `sexo` | string | export | `M` or `F` |

Note:
- `ano` is not part of the SIH jobs/UI schema.
- `mes` is not part of the SIH jobs/UI schema; use the collection-level
  `months` field when month selection is needed.
- SIH discovery uses the PySUS FTP catalog. Broad selections such as all states,
  all months, and multiple years can resolve to thousands of DBC files and many
  gigabytes before export filtering is applied.
- Use `POST /sources/sih/discovery` to inspect file count, estimated byte size,
  grouping, and a sample before creating large SIH jobs.

### 3.9 NASA POWER (`nasa_power`)

Single-point climate series from the NASA POWER API (no authentication).

| Parameter | Type | Phase | Notes |
| --- | --- | --- | --- |
| `output_dir` | string | tecnica | Output folder, defaulting to `Guaraci Downloads` on the Desktop |
| `output_format` | string | exportacao | `csv`, `parquet`, `sqlite` |
| `latitude` | string | coleta | Point latitude, decimal degrees (`-90` to `90`); e.g. `-23.55` |
| `longitude` | string | coleta | Point longitude, decimal degrees (`-180` to `180`); e.g. `-46.63` |
| `start_date` | string | coleta | Window start (`YYYY-MM-DD`); POWER daily coverage starts in 1981 |
| `end_date` | string | coleta | Window end (`YYYY-MM-DD`) |
| `parameters` | string_list | coleta | POWER variable codes (curated list, e.g. `T2M`, `T2M_MAX`, `T2M_MIN`, `PRECTOTCORR`, `RH2M`, `WS2M`, `ALLSKY_SFC_SW_DWN`) |
| `temporal` | string | coleta | `daily` (default) or `monthly` |
| `community` | string | tecnica | `AG` (default), `RE`, or `SB` |
| `keep_raw` | boolean | tecnica | Save the raw JSON response; default `false` |
| `timeout` | integer | tecnica | HTTP timeout in seconds (default `120`) |
| `api_base_url` | string | tecnica | Optional POWER base URL override |

NASA POWER notes:
- Latitude/longitude are the native point inputs; municipality-centroid lookup
  is intentionally left as future work (it would require an IBGE coordinate
  dataset, itself a separate primary-source integration).
- Output is a tidy wide table: one row per period, one column per variable,
  plus derived `period`, `date`, `year`, `month`, `day`, and point columns.
- For `monthly`, POWER's annual aggregate is preserved as `month=13` (no
  `date`); filter `month <= 12` for strictly monthly observations.
- The missing-data sentinel is read from the response `header.fill_value`
  (commonly `-999`) and converted to null.
- Like OpenDataSUS, leaving both `output_format` empty and `keep_raw=false`
  produces only a manifest and emits an `export_warning`.

### 3.10 NASA FIRMS (`nasa_firms`)

Active-fire / thermal-anomaly detections from the NASA FIRMS CSV API.

| Parameter | Type | Phase | Notes |
| --- | --- | --- | --- |
| `output_dir` | string | tecnica | Output folder, defaulting to `Guaraci Downloads` on the Desktop |
| `output_format` | string | exportacao | `csv`, `parquet`, `sqlite` |
| `start_date` | string | coleta | Window start (`YYYY-MM-DD`) |
| `end_date` | string | coleta | Window end (`YYYY-MM-DD`); long windows are chunked into <=10-day requests |
| `product` | string | coleta | FIRMS source product: `VIIRS_SNPP_NRT` (default), `VIIRS_NOAA20_NRT`, `VIIRS_NOAA21_NRT`, `MODIS_NRT`, `VIIRS_SNPP_SP`, `MODIS_SP` |
| `country` | string | coleta | 3-letter ISO country code (default `BRA`); ignored when `area` is set |
| `area` | string | coleta | Optional bounding box `west,south,east,north` or `world`; overrides `country` |
| `keep_raw` | boolean | tecnica | Save the raw CSV; default `false` |
| `timeout` | integer | tecnica | HTTP timeout in seconds (default `120`) |
| `api_base_url` | string | tecnica | Optional FIRMS base URL override |

NASA FIRMS notes:
- **MAP_KEY is required and is a credential.** It is read only from the
  `GUARACI_FIRMS_MAP_KEY` environment variable — never a job parameter (which
  would be persisted to disk) and never written to the manifest. Get a free key
  at `https://firms.modaps.eosdis.nasa.gov/api/map_key/`.
- The user-facing field is named `product` (not `source`) to avoid colliding
  with the `DownloadService.run` `source` argument; it maps to the FIRMS API's
  "source" path segment.
- Output is the FIRMS CSV columns (which differ between MODIS and VIIRS) plus a
  `firms_product` column recording the selected product.
- `NRT` products are near-real-time; `SP` products are standard-processing
  (archive) and lag by a longer interval.

### 3.11 NASA GPM IMERG (`nasa_gpm`)

Daily GPM IMERG precipitation for a single point, via GES DISC OPeNDAP
subsetting (no HDF5/NetCDF download or parsing; no extra dependency).

| Parameter | Type | Phase | Notes |
| --- | --- | --- | --- |
| `output_dir` | string | tecnica | Output folder, defaulting to `Guaraci Downloads` on the Desktop |
| `output_format` | string | exportacao | `csv`, `parquet`, `sqlite` |
| `latitude` | string | coleta | Point latitude, decimal degrees (`-90` to `90`); e.g. `-23.55` |
| `longitude` | string | coleta | Point longitude, decimal degrees (`-180` to `180`); e.g. `-46.63` |
| `start_date` | string | coleta | Window start (`YYYY-MM-DD`); one request per day, window capped at ~1 year |
| `end_date` | string | coleta | Window end (`YYYY-MM-DD`) |
| `variable` | string | coleta | IMERG variable: `precipitation` (default), `MWprecipitation`, `randomError`, `precipitation_cnt` |
| `product` | string | coleta | Temporal product; only `daily` (GPM_3IMERGDF V07) for now |
| `keep_raw` | boolean | tecnica | Save the raw OPeNDAP ASCII responses; default `false` |
| `timeout` | integer | tecnica | HTTP timeout in seconds (default `120`) |
| `api_base_url` | string | tecnica | Optional GES DISC OPeNDAP base URL override |

NASA GPM notes:
- **Earthdata token required and is a credential.** It is read only from the
  `GUARACI_EARTHDATA_TOKEN` environment variable — never a job parameter and
  never written to the manifest. Generate one at `https://urs.earthdata.nasa.gov`.
- **The account must authorize the "NASA GESDISC DATA ARCHIVE" application**
  (urs.earthdata.nasa.gov -> Applications -> Authorized Apps). Without it, data
  requests return HTTP 401 even with a valid token. This is the current
  experimental gate; the OPeNDAP contract itself is validated.
- Output is a tidy table: `date`, `year`, `month`, `day`, `latitude`,
  `longitude`, and the requested `variable`; the IMERG fill value becomes null.
- Half-hourly and monthly products are not exposed yet (daily only); the
  Giovanni time-series API was evaluated and rejected (server-side 500s).

## 4. UI and API Versus Direct CLI

The jobs UI and API strictly follow the `DownloadService` schema.

The generic CLI group `guaraci fetch` is the schema-driven path to **any**
registered source (DATASUS FTP, OpenDataSUS, NASA, gov.br) from the terminal:

- `guaraci fetch list` — every registered source.
- `guaraci fetch schema <source>` — its parameters (name, type, required, default).
- `guaraci fetch run <source> --set KEY=VALUE ... [--format csv|parquet|sqlite] [-o DIR]`.
- `guaraci fetch discover <source> --set start_year=… --set end_year=… [--sizes]` —
  preflight for DATASUS FTP sources: file count broken down by group/UF, plus the
  total download size with `--sizes`, **without downloading**.

`--set` values are coerced to the type declared by the schema; omit `--format`
to download/collect without exporting. NASA credentials are read only from the
environment (`GUARACI_FIRMS_MAP_KEY`, `GUARACI_EARTHDATA_TOKEN`), never as flags.

The direct source CLIs (`sinan_cli`, `sim_cli`, `sih_cli`) may still expose historical options.
Current example:
- `sih_cli` still includes `--ano` for local dataframe filtering.

## 5. Legacy SNIS (BigQuery)

The legacy flow remains available in the CLI:
- `python -m guaraci.cli.snis_cli download-legacy`
- `python -m guaraci.cli.snis_cli schema-legacy`

Legacy implementation:
- `guaraci/snis/legacy/bigquery.py`

It is not the recommended primary path for current SNIS usage.

## 6. Recommended Usage Practices

1. Start with the smallest time window and the narrowest filters possible.
2. Set `output_format` only when you need a final exported dataset.
3. For crawler sources, combine `modules` and `file_kinds` to reduce noise.
4. Monitor `export_warning` to detect empty exports.


---
? [Índice da documentação](README.md) · [Voltar ao projeto](../README.md)

