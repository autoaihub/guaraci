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
- `srag_arquivos` (`opendatasus files`) — primary: `dadosabertos.saude.gov.br/dataset/srag-2019-a-2026`
  (SRAG annual "banco vivo" bulk files, S3-hosted; discovered by scraping the
  portal, not a CKAN/DEMAS API — see §3.5)
- `sisagua_controle_mensal_parametros_basicos` (`opendatasus files`) — primary:
  `dadosabertos.saude.gov.br/dataset/sisagua-controle-mensal-parametros-basicos`
- `sisagua_controle_semestral` (`opendatasus files`) — primary:
  `dadosabertos.saude.gov.br/dataset/sisagua-controle-semestral`
- `sisagua_vigilancia_parametros_basicos` (`opendatasus files`) — primary:
  `dadosabertos.saude.gov.br/dataset/sisagua-vigilancia-parametros-basicos`
- `sisagua_tratamento_agua` (`opendatasus files`) — primary:
  `dadosabertos.saude.gov.br/dataset/sisagua-tratamento-de-agua`
- `sisagua_populacao_abastecida` (`opendatasus files`) — primary:
  `dadosabertos.saude.gov.br/dataset/sisagua-populacao-abastecida`
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
- `ibge_populacao` (`ibge api`) — primary: `servicodados.ibge.gov.br/api/v3/agregados`
  (IBGE SIDRA aggregates, keyless JSON; population estimates, table 6579)
- `ibge_pib_municipios` (`ibge api`) — primary: same SIDRA API
  (municipal GDP / PIB, table 5938)
- `ibge_populacao_idade_sexo` (`ibge api`) — primary: same SIDRA API
  (census population by sex and age, table 9514; denominator/socioeconomic
  layers for health rates)

Convention:
- Always use the canonical `source` value returned by `GET /sources`.
- The `mode` field on `GET /sources` describes the transport, not the
  publisher. `pysus ftp` means "DATASUS FTP, fetched through PySUS"; the
  fetch layer may change without
  altering the source identity.

### Canonical parameter vocabulary

Same concept, canonical names by family (aliases are not accepted — the schema
rejects unknown parameters):

- **UF / state**: `states` (list) on DATASUS collection params (SIM/SIH/SINAN
  and FTP spec systems); `uf` (single value) on refinement/export filters and
  OpenDataSUS sources.
- **Year range**: `start_year` / `end_year` everywhere a range applies.
- **Date range**: `start_date` / `end_date` (ISO `YYYY-MM-DD`) on NASA sources.
- **Case-insensitivity**: UF and group values are normalized before
  validation — `states=["sp"]` and `uf="sp"` are accepted and coerced to
  upper case across all sources.

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

### 3.5 OpenDataSUS Bulk Files (`srag_arquivos`, `sisagua_controle_mensal_parametros_basicos`, `sisagua_controle_semestral`, `sisagua_vigilancia_parametros_basicos`, `sisagua_tratamento_agua`, `sisagua_populacao_abastecida`)

| Parameter | Type | Phase | Notes |
| --- | --- | --- | --- |
| `output_dir` | string | download | Output folder, defaulting to `Guaraci Downloads` on the Desktop |
| `output_format` | string | export | `csv`, `parquet`, `sqlite` — converts the raw resource; omit to keep it as-is |
| `start_year` | integer | download | Initial year filter; no-op for the two cumulative SISAGUA sources below |
| `end_year` | integer | download | Final year filter; no-op for the two cumulative SISAGUA sources below |
| `resource_filter` | string | local refinement | Substring filter (case-insensitive) on the resource's display name, in addition to the year filter |
| `keep_raw` | boolean | download | Keep the originally downloaded raw file after a successful `output_format` conversion, default `false` (large files are discarded once converted) |
| `timeout` | integer | download | HTTP timeout in seconds for portal/S3 requests |
| `api_base_url` | string | download | Optional `dadosabertos.saude.gov.br` base URL override |

Bulk-files notes:
- Different transport from the record-oriented OpenDataSUS sources above:
  each "dataset" here is a handful of whole-file resources (CSV/Parquet/JSON/
  XML, sometimes zipped) hosted on a public S3 bucket
  (`s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/...`), not a CKAN datastore
  or a paginated DEMAS JSON API. The CKAN API on the current portal host is
  unavailable (verified 2026-08-17: `ckan-dadosabertos.saude.gov.br` does not
  resolve; `dadosabertos.saude.gov.br/api/3/action/...` returns 404).
- Discovery is a 2-hop HTML scrape (dataset page -> resource page -> S3 URL),
  stdlib-only (`html.parser`), implemented in
  `guaraci/opendatasus/portal_files.py`. `guaraci fetch discover
  <source> --set start_year=... --set end_year=...` lists matching resources
  (name/format/year/URL, optionally size with `--sizes`) without downloading.
- One resource is selected per year (or one overall, for the two cumulative
  SISAGUA packages that have no year segmentation), preferring the highest
  format in the source's `format_priority` (`parquet` > `csv` > `json` >
  `xml` for SRAG; SISAGUA has no parquet, so `csv` > `json` > `xml`).
- **SISAGUA files are `.zip` archives**, not raw CSV/Parquet directly
  (verified live 2026-08-17 — e.g. `cadastro_populacao_abastecida_csv.zip`).
  `output_format` conversion is only implemented for raw `csv`/`parquet`
  resources; requesting a conversion on a SISAGUA `.zip` resource produces an
  `export_warning` rather than a silent failure (the raw `.zip` is still
  materialized on disk).
- Idempotency is by basename under `output_dir`: a second run with the same
  params skips files that already exist. SRAG's current ("banco vivo") year
  basename embeds its extraction date and changes weekly, so it naturally
  re-downloads; other years are stable until the portal republishes them.
- `sisagua_controle_mensal_parametros_basicos` is a GRANDE dataset
  (potentially millions of rows per year) — always scope `start_year`/
  `end_year` narrowly; the schema description and `discover()` payload both
  carry a warning note.
- Only 5 of the 14 SISAGUA packages listed on the portal are registered so
  far (the ones judged most broadly useful); the remaining 9 use the exact
  same transport and are a trivial follow-up — see `docs/handoffs/_QUADRO.md`.
- SIOPS was investigated but NOT registered: its portal dataset only exposes
  a metadata PDF via S3 (no tabular resource), and its own API
  (`siops-consulta-publica-api.saude.gov.br`) does not publish a discoverable
  Swagger/OpenAPI spec (`/swagger-resources` returns `[]`; all standard
  springdoc paths return 404) — see `docs/handoffs/_QUADRO.md`.

### 3.6 Auto-generated OpenDataSUS DEMAS sources

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

### 3.7 SINAN (`sinan`)

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

### 3.8 SIM (`sim`)

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

### 3.9 SIH (`sih`)

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

### 3.10 NASA POWER (`nasa_power`)

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

### 3.11 NASA FIRMS (`nasa_firms`)

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

### 3.12 NASA GPM IMERG (`nasa_gpm`)

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

### 3.13 IBGE Population Estimates (`ibge_populacao`)

Annual TCU population estimates by locality x year, from SIDRA aggregate table
6579 (variable 9324). The keyless JSON aggregates API is swept one year at a time.

| Parameter | Type | Phase | Notes |
| --- | --- | --- | --- |
| `output_dir` | string | tecnica | Output folder, defaulting to `Guaraci Downloads` on the Desktop |
| `output_format` | string | exportacao | `csv`, `parquet`, `sqlite` |
| `start_year` | integer | coleta | Initial year; table 6579 covers `2001`+ |
| `end_year` | integer | coleta | Final year |
| `level` | string | coleta | Territorial level: `municipio` (default), `uf`, `regiao`, `brasil` |
| `keep_raw` | boolean | tecnica | Save the raw SIDRA JSON response; default `false` |
| `timeout` | integer | tecnica | HTTP timeout in seconds (default `120`) |
| `api_base_url` | string | tecnica | Optional SIDRA base URL override |

### 3.14 IBGE Municipal GDP / PIB (`ibge_pib_municipios`)

Municipal GDP (PIB dos Municípios) from SIDRA table 5938 (variable 37), in
R$ 1000. Same base schema and phases as `ibge_populacao`, with `start_year` /
`end_year` covering `2002`+.

| Parameter | Type | Phase | Notes |
| --- | --- | --- | --- |
| `output_dir` | string | tecnica | Output folder, defaulting to `Guaraci Downloads` on the Desktop |
| `output_format` | string | exportacao | `csv`, `parquet`, `sqlite` |
| `start_year` | integer | coleta | Initial year; table 5938 covers `2002`+ |
| `end_year` | integer | coleta | Final year |
| `level` | string | coleta | Territorial level: `municipio` (default), `uf`, `regiao`, `brasil` |
| `keep_raw` | boolean | tecnica | Save the raw SIDRA JSON response; default `false` |
| `timeout` | integer | tecnica | HTTP timeout in seconds (default `120`) |
| `api_base_url` | string | tecnica | Optional SIDRA base URL override |

### 3.15 IBGE Census Population by Sex and Age (`ibge_populacao_idade_sexo`)

Census population (2022 reference) from SIDRA table 9514 (variable 93), split by
sex and age classification — the denominators for age-standardised rates. The
default level is `uf` (municipal breakdown is a much larger extract).

| Parameter | Type | Phase | Notes |
| --- | --- | --- | --- |
| `output_dir` | string | tecnica | Output folder, defaulting to `Guaraci Downloads` on the Desktop |
| `output_format` | string | exportacao | `csv`, `parquet`, `sqlite` |
| `start_year` | integer | coleta | Initial year; census reference is `2022` |
| `end_year` | integer | coleta | Final year |
| `level` | string | coleta | Territorial level: `uf` (default), `municipio`, `regiao`, `brasil` |
| `sexo` | string | coleta | Sex slice: `ambos` (default), `homens`, `mulheres`, `total` |
| `faixa_etaria` | string | coleta | Age slice: `quinquenal` (5-year groups, default), `total`, `todos` (all detailed ages) |
| `keep_raw` | boolean | tecnica | Save the raw SIDRA JSON response; default `false` |
| `timeout` | integer | tecnica | HTTP timeout in seconds (default `120`) |
| `api_base_url` | string | tecnica | Optional SIDRA base URL override |

IBGE notes:
- Output is one tidy row per `(nivel, localidade_id, ano[, classification …])`:
  `nivel, localidade_id, localidade_nome, ano, [<classif> …], variavel_id,
  unidade, valor`. For `ibge_populacao_idade_sexo` the classification columns
  are `sexo`, `idade`, and `forma_de_declaracao_da_idade`.
- SIDRA missing markers (`-`, `..`, `...`, `x`) become null; a year with no data
  is skipped with a warning, not a failure.
- No credential is required (keyless API). Like OpenDataSUS and NASA, leaving
  `output_format` empty and `keep_raw=false` produces only a manifest and emits
  an `export_warning`.

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

