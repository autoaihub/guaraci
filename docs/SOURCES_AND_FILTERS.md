# Sources and Filters

Reference document for the parameters exposed through the schema, API, and UI.

## 1. Execution Phases

For DATASUS sources, parameters can act in different phases:

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
- `srag_arquivos_2009_2012` and `srag_arquivos_2013_2018` (`opendatasus files`), primary:
  `dadosabertos.saude.gov.br/dataset/srag-2009-2012` and `.../srag-2013-2018`
- `sesai_tuberculose` (`opendatasus files`), primary: `dadosabertos.saude.gov.br/dataset/tuberculose_sesai`
- `enani_2019` (`opendatasus files`), primary:
  `dadosabertos.saude.gov.br/dataset/estudo-nacional-de-alimentacao-e-nutricao-infantil-enani-2019`
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
- `sisagua_controle_mensal_demais_parametros` (`opendatasus files`) — primary:
  `dadosabertos.saude.gov.br/dataset/sisagua-controle-mensal-demais-parametros`
- `sisagua_controle_mensal_amostras_fora_do_padrao` (`opendatasus files`) — primary:
  `dadosabertos.saude.gov.br/dataset/sisagua-controle-mensal-amostras-fora-do-padrao`
- `sisagua_controle_mensal_plano_amostragem` (`opendatasus files`) — primary:
  `dadosabertos.saude.gov.br/dataset/sisagua-controle-mensal-plano-amostragem`
  (year-segmented 2014-2026, like the other "controle mensal" packages)
- `sisagua_controle_mensal_infraestrutura_operacional` (`opendatasus files`) — primary:
  `dadosabertos.saude.gov.br/dataset/sisagua-controle-mensal-infraestrutura-operacional`
- `sisagua_vigilancia_demais_parametros` (`opendatasus files`) — primary:
  `dadosabertos.saude.gov.br/dataset/sisagua-vigilancia-demais-parametros`
- `sisagua_vigilancia_cianobacterias_e_cianotoxinas` (`opendatasus files`) — primary:
  `dadosabertos.saude.gov.br/dataset/sisagua-vigilancia-cianobacterias-e-cianotoxinas`
- `sisagua_pontos_de_captacao` (`opendatasus files`) — primary:
  `dadosabertos.saude.gov.br/dataset/sisagua-pontos-de-captacao`
- `sisagua_cadastro_carro_pipa_procedencia` (`opendatasus files`) — primary:
  `dadosabertos.saude.gov.br/dataset/sisagua-cadastro-carro-pipa-procedencia`
- `sisagua_cadastro_carro_pipa_populacao` (`opendatasus files`) — primary:
  `dadosabertos.saude.gov.br/dataset/sisagua-cadastro-carro-pipa-populacao`
- `sinan` (`datasus ftp`) — primary: `ftp.datasus.gov.br/dissemin/publicos/SINAN/`
- `sim` (`datasus ftp`) — primary: `ftp.datasus.gov.br/dissemin/publicos/SIM/`
- `sih` (`datasus ftp`) — primary: `ftp.datasus.gov.br/dissemin/publicos/SIHSUS/`
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
- `inmet_estacoes` (`inmet portal zip`) — primary: `portal.inmet.gov.br`
  (INMET automatic weather stations, hourly historical series, one ZIP per
  year 2000-present; no third-party mirror involved)
- `ibge_nascidos_vivos_rc` (`ibge api`) — primary: same SIDRA API
  (registro civil, live births by month/sex, table 2680; counterpoint to
  DATASUS SINASC)
- `ibge_obitos_rc` (`ibge api`) — primary: same SIDRA API
  (registro civil, deaths by month/sex, table 2681; counterpoint to
  DATASUS SIM)
- `ibge_area_territorial` (`ibge api`) — primary: same SIDRA API
  (area / density / population, census-2022 reference, table 4714; spatial
  denominator layer)
- `ibge_casamentos` (`ibge api`): primary: same SIDRA API
  (registro civil, marriages by month of registration, table 4406; closes the
  registro civil series alongside nascidos vivos e óbitos)
- `ibge_divorcios` (`ibge api`): primary: same SIDRA API
  (registro civil, divorces granted in 1st instance, table 5937)
- `ibge_saneamento_agua` (`ibge api`): primary: same SIDRA API
  (Censo 2022, households by main water supply, table 6803; determinant
  social layer paired with SISAGUA)
- `ibge_saneamento_esgoto` (`ibge api`): primary: same SIDRA API
  (Censo 2022, households by sanitary sewage type, table 6805)
- `ibge_saneamento_lixo` (`ibge api`): primary: same SIDRA API
  (Censo 2022, households by garbage disposal, table 6892)
- `ana_hidro` (`ana hidro api`) — primary: `www.ana.gov.br/hidrowebservice`
  (ANA/SNIRH HidroWebService telemetric stations: chuva/nível/vazão; requires
  an identifier+password credential obtained by e-mail registration with ANA;
  experimental — live payload validation is pending that registration)
- `inpe_queimadas` (`inpe queimadas api`) — primary: `dataserver-coids.inpe.br`
  (INPE Queimadas/BDQueimadas fire-spot detections; annual reference product
  since 2003, monthly product since 2023). Complements — does not replace —
  `nasa_firms`: FIRMS is NASA's global near-real-time MODIS/VIIRS feed,
  while INPE Queimadas is Brazil's own national program with its own
  satellite-reference methodology and locally derived `bioma`/`municipio`
  classification.
- `cetesb_qualar` (`cetesb qualar api`) — primary: `servicos.cetesb.sp.gov.br/arcgis`
  (CETESB QUALAR, hourly air quality INDEX for six pollutants across 62
  stations, rolling 48-hour window; the values are not concentrations — see
  §3.23). First state-level publisher in the catalogue.
- `cetesb_estacoes` (`cetesb qualar api`) — primary: same ArcGIS service
  (geolocated registry of the monitoring stations, with the current index)
- `cetesb_qualar_horario` (`cetesb qualar auth`) — primary:
  `qualar.cetesb.sp.gov.br/qualar` (the classic QUALAR system: measured hourly
  CONCENTRATION for 12 pollutants and 8 meteorological variables, full
  historical range. Requires a free CETESB account; see §3.24)
- eight ANVISA sources (`anvisa files`), primary: `dados.anvisa.gov.br/dados/`
  (whole files republished over the previous ones; see §3.25):
  `anvisa_vigimed_notificacoes`, `anvisa_vigimed_medicamentos`,
  `anvisa_vigimed_reacoes`, `anvisa_tecnovigilancia`, `anvisa_hemovigilancia`,
  `anvisa_medicamentos_registrados`, `anvisa_cmed_precos`,
  `anvisa_cmed_precos_governo`

### Navigating by subject: themes and presets

The catalogue above has 116 entries, and the subject a user is after rarely
coincides with the boundary of a source. Two layers exist for that.

**Themes** (`guaraci/services/themes.py`) answer "where is the data on this
subject?". Twenty slugs, every registered source classified, listed by
`GET /themes` or `guaraci fetch themes`, and usable as a filter
(`GET /sources?theme=oncologia`, `guaraci fetch list --theme oncologia`). A
source may carry several themes; `sim` is both `mortalidade` and `oncologia`.

The classification lives in one central map, not in the `SourceDescriptor`
built by each module under `guaraci/services/sources/`. The adapters never
declare a theme: `DownloadService.list_sources` attaches it on read. Generated
families (`sisagua_*`, `saude_indigena_*`, `atencao_primaria_*`) are matched by
prefix rules so the map does not rot as the DEMAS Swagger grows.

**Presets** (`guaraci/services/presets.py`) answer the next question, "with
which parameters do I pull it?", across sources. Listed by `GET /presets` or
`guaraci fetch presets`; detailed by `GET /presets/{name}` or
`guaraci fetch preset <name>`.

| Preset | Sources |
| --- | --- |
| `oncologia` | `siscan` (`CC`,`CM`), `sia` (`AQ`,`AR`), `painel_oncologia`, `sih`, `sim` |
| `nascimentos` | `sinasc`, `ibge_nascidos_vivos_rc`, `sisprenatal`, `ibge_populacao` |

Each step declares the phase its cut happens in. `siscan` and `sia` come out of
collection already cut; `sih` and `sim` arrive whole, because the DATASUS FTP
offers no CID filter at the origin, and the step's `refine` field names the
column to filter afterwards. Read `caveats` before using a preset: it states
what the cut does *not* contain. `oncologia`, in particular, has no incidence
data, for the reason given in §2 about primary publishers.

Convention:
- Always use the canonical `source` value returned by `GET /sources`.
- The `mode` field on `GET /sources` describes the transport, not the
  publisher. `datasus ftp` means "fetched straight from the DATASUS FTP"; the
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

Cost of date and UF refinements (measured against `/arboviroses/dengue`):
- The DEMAS endpoints accept only `nu_ano`, `limit` and `offset`. `start_date`,
  `end_date` and `uf` are **local** refinements: the collection pages through
  the whole year and discards the rows outside the window client-side. Asking
  for a single month therefore costs the same as asking for the whole year.
- Dengue 2024 holds over 4 million records, paginated at roughly 200 records
  per second, so a complete year takes on the order of 5 hours. The default
  `max_pages=250` with `batch_size=1000` stops at 250 000 records, about 6% of
  that year, and the result is reported with `status=partial_success` plus a
  truncation warning. Raise `max_pages` deliberately, and expect the runtime
  to scale with it.
- Records no longer accumulate in memory: past 5 000 rows the collection spills
  to parquet parts and the final file is written by streaming. Measured over
  60 000 dengue records, peak memory drops from 1696 MB to 593 MB, at a cost of
  12% in runtime. Each record costs about 11 KB while held as a dictionary, so
  a full year would previously have required roughly 45 GB of RAM.

### 3.5 OpenDataSUS Bulk Files (`srag_arquivos`, `srag_arquivos_2009_2012`, `srag_arquivos_2013_2018`, `sesai_tuberculose`, `enani_2019` + all 14 SISAGUA packages: `sisagua_controle_mensal_parametros_basicos`, `sisagua_controle_semestral`, `sisagua_vigilancia_parametros_basicos`, `sisagua_tratamento_agua`, `sisagua_populacao_abastecida`, `sisagua_controle_mensal_demais_parametros`, `sisagua_controle_mensal_amostras_fora_do_padrao`, `sisagua_controle_mensal_plano_amostragem`, `sisagua_controle_mensal_infraestrutura_operacional`, `sisagua_vigilancia_demais_parametros`, `sisagua_vigilancia_cianobacterias_e_cianotoxinas`, `sisagua_pontos_de_captacao`, `sisagua_cadastro_carro_pipa_procedencia`, `sisagua_cadastro_carro_pipa_populacao`)

| Parameter | Type | Phase | Notes |
| --- | --- | --- | --- |
| `output_dir` | string | download | Output folder, defaulting to `Guaraci Downloads` on the Desktop |
| `output_format` | string | export | `csv`, `parquet`, `sqlite` — converts the raw resource; omit to keep it as-is |
| `start_year` | integer | download | Initial year filter; no-op for the cumulative SISAGUA sources (all except the "controle mensal" packages, which are year-segmented) |
| `end_year` | integer | download | Final year filter; same cumulative-source caveat as `start_year` |
| `resource_filter` | string | local refinement | Substring filter (case-insensitive) on the resource's display name, in addition to the year filter |
| `keep_raw` | boolean | download | Keep the originally downloaded raw file after a successful `output_format` conversion, default `false` (large files are discarded once converted) |
| `timeout` | integer | download | HTTP timeout in seconds for portal/S3 requests |
| `api_base_url` | string | download | Optional `dadosabertos.saude.gov.br` base URL override |

Bulk-files notes:
- **Historical SRAG banks** (`srag_arquivos_2009_2012`, `srag_arquivos_2013_2018`):
  frozen SINAN Influenza files, one per year, in a layout that predates the
  SIVEP-Gripe one used by `srag_arquivos` (113 and 114 columns against 194;
  names and codes differ, so the three sources do not stack without a
  mapping). Verified live on 2026-09-24: 125 250 rows for 2009-2012 (88 354 in
  2009 alone, the H1N1 pandemic) and 201 799 for 2013-2018. Each year is
  listed three times with no format in its name; the CSV is not on the S3
  bucket but on the Ministry's CloudFront distribution linked from the
  resource page, which the scraper accepts as a fallback when the page has no
  S3 link. The aggregate "2009 a 2012" resource is excluded. `start_year` and
  `end_year` are bounded to the bank's own years, and the orchestrator stops
  re-checking a bank once its last year is in the ledger.
- **`sesai_tuberculose`**: tuberculosis cases in indigenous health (SIASI),
  one `csv.zip` per year; only 2022 is published (505 cases, verified live
  2026-09-24). The patient id comes de-identified from the source.
- **`enani_2019`**: the 2019 national child nutrition survey, a one-off
  edition. One `csv.zip` of 223 MB holding 26 banks (about 2.7 GB open):
  `data_crianca_calib_anon` and 25 imputed copies `data_bioq_calib_anon_*`,
  all with 741 columns and 14 558 children. Read the source's imputation
  note before pooling the copies. The orchestrator writes each bank as its
  own bronze file, suffixed with the bank's name.
- **Every SRAG CSV is `;`-separated**, and the 2016 file is latin-1 (with a
  few characters already corrupted at the source). Conversion detects the
  separator from the header and reads non-UTF-8 files through a transcoded
  temporary copy; the downloaded file itself is never altered.
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
- One resource is selected per year (or one overall, for the cumulative
  SISAGUA packages that have no year segmentation). Only
  `sisagua_controle_mensal_parametros_basicos` and
  `sisagua_controle_mensal_plano_amostragem` are year-segmented (2014-2026,
  verified live); every other SISAGUA package (including the other three
  "controle mensal" ones — demais parâmetros, amostras fora do padrão,
  infraestrutura operacional) is cumulative with no year in the resource
  name. Selection prefers the highest format in the source's
  `format_priority` (`parquet` > `csv` > `json` > `xml` for SRAG; SISAGUA has
  no parquet, so `csv` > `json` > `xml`).
- **SISAGUA files are `.zip` archives**, not raw CSV/Parquet directly
  (verified live 2026-08-17 — e.g. `cadastro_populacao_abastecida_csv.zip`).
  Since 2026-09-24 a `.zip` holding CSV is extracted (streaming, member
  basename only, so no zip slip) and each inner CSV is converted; a zip with
  several CSVs yields one export per CSV. A zip with no CSV inside (the JSON
  and XML variants) still raises an explicit `export_warning`. Before this,
  every SISAGUA conversion aborted, and the orchestrator recorded `empty` for
  all 14 SISAGUA sources on every run, so none of them had reached bronze.
- **Cumulative packages are monthly snapshots in the orchestrator.** The ten
  SISAGUA packages with no year segmentation (`CUMULATIVE_SOURCES` in
  `guaraci/services/sources/opendatasus_files.py`) republish one file with
  the current state; the sweep stores one dated copy per month instead of
  asking for the same file once per year.
- Idempotency is by basename under `output_dir`: a second run with the same
  params skips files that already exist. SRAG's current ("banco vivo") year
  basename embeds its extraction date and changes weekly, so it naturally
  re-downloads; other years are stable until the portal republishes them.
- `sisagua_controle_mensal_parametros_basicos`, `sisagua_controle_mensal_demais_parametros`,
  `sisagua_controle_mensal_amostras_fora_do_padrao`,
  `sisagua_controle_mensal_infraestrutura_operacional`,
  `sisagua_controle_mensal_plano_amostragem` and `sisagua_vigilancia_demais_parametros`
  are GRANDE datasets (potentially millions of rows; compressed sizes of
  ~39-138MB verified live 2026-08-18) — always scope `start_year`/`end_year`
  narrowly for the year-segmented ones; the schema description and
  `discover()` payload both carry a warning note.
- All 14 SISAGUA packages listed on the portal are now registered
  (verified live 2026-08-18); SIOPS remains the only investigated-but-not-
  registered dataset in this family (see below).
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
- `uf` resolves to the first populated column among `SG_UF_NOT`, `SG_UF`, `UF`
  and `ID_MN_RESI`, in that order, and accepts either the two-letter code or
  the IBGE numeric code. The preference matters because `UF` is present but
  blank in about 96% of the records, while `SG_UF_NOT` (state of notification)
  is complete. The column actually used is reported in the run log.
- `municipio` matches the IBGE municipality **code** as a substring (for
  example `355030`), not the municipality name.
- `faixa_etaria` is the raw DATASUS age code in `NU_IDADE_N`, where the leading
  digit is the unit and the rest is the value: `4023` means 23 years.

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

Notes:
- SIM files carry no dedicated state column: `uf` is read from the first two
  digits of `CODMUNRES`, the municipality of residence. Both the two-letter
  code and the IBGE numeric code are accepted.
- `sexo` is exposed as `M`/`F` and translated to the codes SIM stores
  (`1` masculine, `2` feminine, `0` unknown).
- `ano_obito` falls back to the last four digits of `DTOBITO`, which is stored
  as `DDMMAAAA`, when the file has no `ANOOBITO` column.

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
- `uf` reads `UF_ZI`, which holds the six-digit manager code (`120000` for
  Acre), and falls back to `MUNIC_RES` when `UF_ZI` is empty. The two describe
  different things: the first is the managing unit, the second the patient's
  municipality of residence, so results can differ for patients treated
  outside their home state. The column actually used is reported in the run
  log.
- `sexo` is exposed as `M`/`F` and translated to the codes SIH stores
  (`1` masculine, `3` feminine), inherited from the older AIH layout.
- SIH discovery uses the DATASUS FTP catalog. Broad selections such as all states,
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

### 3.15 IBGE Nascidos Vivos — Registro Civil (`ibge_nascidos_vivos_rc`)

Live births by year, from SIDRA table 2680 (variable 218) — "ocorridos no ano,
por mês do nascimento[...]". Annual periods 2003-2024. Captures **cartorial
registration** (the civil registry), a counterpoint to DATASUS SINASC, which
captures the health-system side (declaração de nascido vivo). Reference total
verified live 2026-08-17: Brasil, 2023, `mes`/`sexo`=`total` → **2 523 267**
live births.

| Parameter | Type | Phase | Notes |
| --- | --- | --- | --- |
| `output_dir` | string | tecnica | Output folder, defaulting to `Guaraci Downloads` on the Desktop |
| `output_format` | string | exportacao | `csv`, `parquet`, `sqlite` |
| `start_year` | integer | coleta | Initial year (`2003`+) |
| `end_year` | integer | coleta | Final year |
| `level` | string | coleta | Territorial level: `municipio` (default), `uf`, `regiao`, `brasil` |
| `mes` | string | coleta | Month-of-birth slice: `total` (default, matches the annual table 2679) or `all` (monthly breakdown) |
| `sexo` | string | coleta | Sex slice: `total` (default), `ambos`, `homens`, `mulheres` |
| `keep_raw` | boolean | tecnica | Save the raw SIDRA JSON response; default `false` |
| `timeout` | integer | tecnica | HTTP timeout in seconds (default `120`) |
| `api_base_url` | string | tecnica | Optional SIDRA base URL override |

`mes != "total"` combined with `level="municipio"` is rejected up front
(`ValueError`) — confirmed live 2026-08-17 that SIDRA returns HTTP 500 for
`N6[all]` × all 13 month categories (5570 municipalities × 13 is over the
aggregate limit); `N3[all]` (UF) × all months works fine. Use a coarser level
for the monthly breakdown.

### 3.16 IBGE Óbitos — Registro Civil (`ibge_obitos_rc`)

Deaths by year, from SIDRA table 2681 (variable 343) — "ocorridos no ano, por
mês de ocorrência[...]". Annual periods 2003-2024. Same civil-registry
counterpoint role as `ibge_nascidos_vivos_rc`, but versus DATASUS SIM.
Reference total verified live 2026-08-17: Brasil, 2023, `mes`/`sexo`=`total`
→ **1 429 575** deaths.

| Parameter | Type | Phase | Notes |
| --- | --- | --- | --- |
| `output_dir` | string | tecnica | Output folder, defaulting to `Guaraci Downloads` on the Desktop |
| `output_format` | string | exportacao | `csv`, `parquet`, `sqlite` |
| `start_year` | integer | coleta | Initial year (`2003`+) |
| `end_year` | integer | coleta | Final year |
| `level` | string | coleta | Territorial level: `municipio` (default), `uf`, `regiao`, `brasil` |
| `mes` | string | coleta | Month-of-occurrence slice: `total` (default, matches the annual table 2684) or `all` |
| `sexo` | string | coleta | Sex slice: `total` (default), `ambos`, `homens`, `mulheres` |
| `keep_raw` | boolean | tecnica | Save the raw SIDRA JSON response; default `false` |
| `timeout` | integer | tecnica | HTTP timeout in seconds (default `120`) |
| `api_base_url` | string | tecnica | Optional SIDRA base URL override |

Same `mes`/`level="municipio"` guardrail as `ibge_nascidos_vivos_rc` (SIDRA
500 confirmed live for the same combination on table 2681).

### 3.17 IBGE Área Territorial e Densidade (`ibge_area_territorial`)

Municipal/UF/regional area, resident population and demographic density, from
SIDRA table 4714 — bundles three variables (`93` população residente, `614`
densidade demográfica, `6318` área da unidade territorial em km²) in one
request via SIDRA's `|`-joined variable list. **Single period, 2022** (census
reference — verified live 2026-08-17 that `periodicidade.inicio ==
periodicidade.fim == 2022`); `start_year`/`end_year` must both be `2022`. The
spatial denominator layer for rate standardisation. Reference total verified
live 2026-08-17: Brasil, 2022 → área territorial **8 510 417.771 km²**.

| Parameter | Type | Phase | Notes |
| --- | --- | --- | --- |
| `output_dir` | string | tecnica | Output folder, defaulting to `Guaraci Downloads` on the Desktop |
| `output_format` | string | exportacao | `csv`, `parquet`, `sqlite` |
| `start_year` | integer | coleta | Must be `2022` (only period published) |
| `end_year` | integer | coleta | Must be `2022` |
| `level` | string | coleta | Territorial level: `municipio` (default), `uf`, `regiao`, `brasil` |
| `keep_raw` | boolean | tecnica | Save the raw SIDRA JSON response; default `false` |
| `timeout` | integer | tecnica | HTTP timeout in seconds (default `120`) |
| `api_base_url` | string | tecnica | Optional SIDRA base URL override |

### 3.18 IBGE Casamentos, Registro Civil (`ibge_casamentos`)

Marriages by year, from SIDRA table 4406 (variable 4993): "por mês do
registro, estado civil dos cônjuges, grupos de idade dos cônjuges e lugar do
registro". Annual periods 2013-2024 (confirmed live 2026-08-25). Closes the
registro civil series alongside `ibge_nascidos_vivos_rc` e `ibge_obitos_rc`.
Only the month-of-registration axis is exposed; estado civil and grupo de
idade of each spouse (four extra classifications, up to 39 age categories
each) stay fixed at Total. Reference total verified live 2026-08-25: Brasil,
2023, `mes="total"` → **940 799 casamentos**.

| Parameter | Type | Phase | Notes |
| --- | --- | --- | --- |
| `output_dir` | string | tecnica | Output folder, defaulting to `Guaraci Downloads` on the Desktop |
| `output_format` | string | exportacao | `csv`, `parquet`, `sqlite` |
| `start_year` | integer | coleta | From 2013 |
| `end_year` | integer | coleta | Up to the current year |
| `level` | string | coleta | Territorial level: `municipio` (default), `uf`, `regiao`, `brasil` |
| `mes` | string | coleta | `total` (default) or `all`; `all` requires `level != municipio` (SIDRA 500 confirmed live for that combination) |
| `keep_raw` | boolean | tecnica | Save the raw SIDRA JSON response; default `false` |
| `timeout` | integer | tecnica | HTTP timeout in seconds (default `120`) |
| `api_base_url` | string | tecnica | Optional SIDRA base URL override |

### 3.19 IBGE Divórcios, Registro Civil (`ibge_divorcios`)

Divorces granted in 1st instance, from SIDRA table 5937 (variable 231):
"por grupos de idade do marido e da mulher na data da sentença, tempo
transcorrido entre as datas do casamento e da sentença e lugar da ação do
processo". Annual periods 2014-2024 (confirmed live 2026-08-25). Unlike the
other registro civil sources, this table has no month axis; instead it has
three age/time classifications, each guarded independently. Reference total
verified live 2026-08-25: Brasil, 2023, all classifications `total` →
**360 787 divórcios**.

| Parameter | Type | Phase | Notes |
| --- | --- | --- | --- |
| `output_dir` | string | tecnica | Output folder, defaulting to `Guaraci Downloads` on the Desktop |
| `output_format` | string | exportacao | `csv`, `parquet`, `sqlite` |
| `start_year` | integer | coleta | From 2014 |
| `end_year` | integer | coleta | Up to the current year |
| `level` | string | coleta | Territorial level: `municipio` (default), `uf`, `regiao`, `brasil` |
| `idade_marido` | string | coleta | `total` (default) or `all`; any of the three axes set to `all` requires `level != municipio` |
| `idade_mulher` | string | coleta | `total` (default) or `all` |
| `tempo_decorrido` | string | coleta | `total` (default) or `all` |
| `keep_raw` | boolean | tecnica | Save the raw SIDRA JSON response; default `false` |
| `timeout` | integer | tecnica | HTTP timeout in seconds (default `120`) |
| `api_base_url` | string | tecnica | Optional SIDRA base URL override |

### 3.20 IBGE Saneamento, Abastecimento de Água (`ibge_saneamento_agua`)

Domicílios particulares permanentes ocupados por forma de abastecimento de
água, do Censo 2022, SIDRA table 6803 (variable 381). **Single period,
2022**; `start_year`/`end_year` must both be `2022`. The determinant social
layer that pairs with the 14 SISAGUA sources and the arbovirus datasets.
Reference total verified live 2026-08-25: Brasil, 2022, `detalhe="total"` →
**72 456 368 domicílios**.

| Parameter | Type | Phase | Notes |
| --- | --- | --- | --- |
| `output_dir` | string | tecnica | Output folder, defaulting to `Guaraci Downloads` on the Desktop |
| `output_format` | string | exportacao | `csv`, `parquet`, `sqlite` |
| `start_year` | integer | coleta | Must be `2022` (only period published) |
| `end_year` | integer | coleta | Must be `2022` |
| `level` | string | coleta | Territorial level: `municipio` (default), `uf`, `regiao`, `brasil` |
| `detalhe` | string | coleta | `total` (default, 1 row/locality) or `all` (18 categories); `all` requires `level != municipio` (SIDRA 500 confirmed live) |
| `keep_raw` | boolean | tecnica | Save the raw SIDRA JSON response; default `false` |
| `timeout` | integer | tecnica | HTTP timeout in seconds (default `120`) |
| `api_base_url` | string | tecnica | Optional SIDRA base URL override |

### 3.21 IBGE Saneamento, Esgotamento Sanitário (`ibge_saneamento_esgoto`)

Domicílios particulares permanentes ocupados por tipo de esgotamento
sanitário, do Censo 2022, SIDRA table 6805 (variable 381). Same shape as
`ibge_saneamento_agua`: single period 2022, `detalhe="all"` (10 categories)
requires `level != municipio` (SIDRA 500 confirmed live). Reference total
verified live 2026-08-25: Brasil, 2022, `detalhe="total"` → **72 456 368
domicílios**.

| Parameter | Type | Phase | Notes |
| --- | --- | --- | --- |
| `output_dir` | string | tecnica | Output folder, defaulting to `Guaraci Downloads` on the Desktop |
| `output_format` | string | exportacao | `csv`, `parquet`, `sqlite` |
| `start_year` | integer | coleta | Must be `2022` (only period published) |
| `end_year` | integer | coleta | Must be `2022` |
| `level` | string | coleta | Territorial level: `municipio` (default), `uf`, `regiao`, `brasil` |
| `detalhe` | string | coleta | `total` (default) or `all` (10 categories); `all` requires `level != municipio` |
| `keep_raw` | boolean | tecnica | Save the raw SIDRA JSON response; default `false` |
| `timeout` | integer | tecnica | HTTP timeout in seconds (default `120`) |
| `api_base_url` | string | tecnica | Optional SIDRA base URL override |

### 3.22 IBGE Saneamento, Destino do Lixo (`ibge_saneamento_lixo`)

Domicílios particulares permanentes ocupados por destino do lixo, do Censo
2022, SIDRA table 6892 (variable 381). Single period 2022. Unlike agua e
esgoto, `detalhe="all"` (8 categories) is confirmed live to work even at
`level="municipio"` (200 OK, ~5.4 MB for 5570 municipalities), so there is
no guard here. Reference total verified live 2026-08-25: Brasil, 2022,
`detalhe="total"` → **72 456 368 domicílios**.

| Parameter | Type | Phase | Notes |
| --- | --- | --- | --- |
| `output_dir` | string | tecnica | Output folder, defaulting to `Guaraci Downloads` on the Desktop |
| `output_format` | string | exportacao | `csv`, `parquet`, `sqlite` |
| `start_year` | integer | coleta | Must be `2022` (only period published) |
| `end_year` | integer | coleta | Must be `2022` |
| `level` | string | coleta | Territorial level: `municipio` (default), `uf`, `regiao`, `brasil` |
| `detalhe` | string | coleta | `total` (default) or `all` (8 categories); `all` also accepted at `level="municipio"` |
| `keep_raw` | boolean | tecnica | Save the raw SIDRA JSON response; default `false` |
| `timeout` | integer | tecnica | HTTP timeout in seconds (default `120`) |
| `api_base_url` | string | tecnica | Optional SIDRA base URL override |

IBGE notes:
- Output is one tidy row per `(nivel, localidade_id, ano[, classification …])`:
  `nivel, localidade_id, localidade_nome, ano, [<classif> …], variavel_id,
  unidade, valor`. For `ibge_populacao_idade_sexo` the classification columns
  are `sexo`, `idade`, and `forma_de_declaracao_da_idade`; for
  `ibge_nascidos_vivos_rc`/`ibge_obitos_rc` they are `mes_do_nascimento` (or
  `mes_de_ocorrencia`) and `sexo`; `ibge_casamentos` has `mes_do_registro`,
  `estado_civil_do_primeiro_conjuge`, `estado_civil_do_segundo_conjuge`,
  `grupo_de_idade_do_primeiro_conjuge`, `grupo_de_idade_do_segundo_conjuge`;
  `ibge_divorcios` has `grupos_de_idade_do_marido_na_data_da_sentenca`,
  `grupos_de_idade_da_mulher_na_data_da_sentenca`,
  `tempo_transcorrido_entre_as_datas_do_casamento_e_da_sentenca`; the three
  `ibge_saneamento_*` sources each have one classification column (`existencia_de_ligacao_a_rede_geral_de_distribuicao_de_agua_e_principal_forma_de_abastecimento_de_agua`,
  `tipo_de_esgotamento_sanitario`, `destino_do_lixo`, respectively);
  `ibge_area_territorial` has no classifications, and `variavel_id`
  distinguishes the three bundled metrics (`93`/`614`/`6318`).
- SIDRA missing markers (`-`, `..`, `...`, `x`) become null; a year with no data
  is skipped with a warning, not a failure.
- No credential is required (keyless API). Like OpenDataSUS and NASA, leaving
  `output_format` empty and `keep_raw=false` produces only a manifest and emits
  an `export_warning`.

### 3.15 INMET Automatic Weather Stations (`inmet_estacoes`)

Hourly historical series from INMET's automatic weather station network.
There is no JSON API: INMET publishes one ZIP per year at
`https://portal.inmet.gov.br/uploads/dadoshistoricos/<AAAA>.zip` holding one
CSV per station (verified live 2026-08-17/18, years 2000-2026; the current
year is a partial, growing archive republished as more months land).
### 3.15 ANA HidroWebService (`ana_hidro`)

Telemetric hydrological series (rain, river level, flow) for one or more ANA/
SNIRH stations, via the new `www.ana.gov.br/hidrowebservice` REST API. The
legacy `telemetriaws1.ana.gov.br` webservice was discontinued 2026-06-30 and
is not used.
### 3.18 INPE Queimadas (`inpe_queimadas`)

Fire-spot ("focos de queimada") detections published by INPE's BDQueimadas
program at `dataserver-coids.inpe.br` (Apache-style file index — years/months
are discovered by parsing the index page, never hardcoded). No credential
required.

| Parameter | Type | Phase | Notes |
| --- | --- | --- | --- |
| `output_dir` | string | tecnica | Output folder, defaulting to `Guaraci Downloads` on the Desktop |
| `output_format` | string | exportacao | `csv`, `parquet`, `sqlite` |
| `start_year` | integer | coleta | Initial year (2000+) |
| `end_year` | integer | coleta | Final year; defaults to `start_year` |
| `ufs` | string_list | coleta | UFs to extract from the yearly ZIP (filtered by station filename); omitted/empty = every station in Brazil |
| `variables` | string_list | coleta | Optional column projection (slug of the original CSV header, e.g. `precipitacao_total_horario_mm`, `temperatura_do_ar_bulbo_seco_horaria_c`); omitted = all columns |
| `keep_raw` | boolean | tecnica | Also keep the original per-station CSVs extracted to disk; default `false` |
| `timeout` | integer | tecnica | HTTP timeout in seconds (default `180`) |
| `api_base_url` | string | tecnica | Optional INMET portal base URL override |

INMET notes:
- **Size**: one year's ZIP holds every automatic station in Brazil — ≈90 MB
  for a full recent year (594 stations), ≈530 KB for the earliest year (2000,
  5 stations). Use `ufs` to keep the extracted/parsed volume small; the ZIP
  itself is always downloaded whole (INMET does not offer per-station
  archives) and cached under `<output_dir>/raw/<year>.zip`.
- **Idempotency / re-check**: a cached ZIP for a past year is never
  re-downloaded. The current year is reconciled by `Content-Length` (a HEAD
  probe) since INMET republishes it with more months over the year.
- Each station CSV starts with 8 metadata lines (region, UF, station name,
  WMO code, latitude, longitude, altitude, foundation date) confirmed on the
  real 2000 and 2025 archives, followed by the tabular header and hourly
  rows. Source encoding is `latin-1`, field separator `;`, decimal separator
  `,`. Missing values are an empty string in recent years and the sentinel
  `-9999` in the earliest (2000-era) files; both are parsed as null.
- Output is one tidy row per `(station, date, hour)`: `year, uf, region,
  station_name, station_code, latitude, longitude, altitude, founded_date,
  date, hour_utc, timestamp`, plus one column per measured variable (slugified
  from the CSV header, e.g. `precipitacao_total_horario_mm`,
  `umidade_relativa_do_ar_horaria`).
- No credential required (keyless, direct file download). Like NASA/IBGE,
  leaving `output_format` empty and `keep_raw=false` produces only a manifest
  and emits an `export_warning`.
| `station_ids` | string_list | coleta | Required. Telemetric station codes; there is no automatic sweep — the station must be known up front |
| `start_date` | string | coleta | Window start (`YYYY-MM-DD`); sliced internally into <=30-day chunks (the API's per-request ceiling) |
| `end_date` | string | coleta | Window end (`YYYY-MM-DD`) |
| `variable` | string | coleta | Required. `chuvas`, `vazoes`, or `cotas` (nível) — labels the request/output; the API itself returns combined station readings |
| `detail` | string | coleta | `adotada` (default, consolidated readings) or `detalhada` (also includes raw sensor readings) |
| `tipo_filtro_data` | string | tecnica | `DATA_LEITURA` (default) or `DATA_ULTIMA_ATUALIZACAO` |
| `keep_raw` | boolean | tecnica | Save the raw JSON responses; default `false` |
| `timeout` | integer | tecnica | HTTP timeout in seconds (default `120`) |
| `api_base_url` | string | tecnica | Optional HidroWebService base URL override |

ANA notes:
- **Credential required.** Identifier + password are obtained by e-mail
  registration with ANA (per the official HidroWebService manual) and read
  only from `GUARACI_ANA_ID`/`GUARACI_ANA_SENHA` — never a job parameter and
  never written to the manifest. **As of this integration, the operator's
  registration was still pending**, so the connector has offline (fake
  client) test coverage only; the opt-in live smoke test
  (`GUARACI_ANA_SMOKE=1`) additionally skips unless both env vars are set.
- Auth (`GET /EstacoesTelemetricas/OAUth/v1`, credentials in the
  `Identificador`/`Senha` headers) returns a `tokenautenticacao` valid for 60
  minutes; the client renews it automatically (proactively, and once more on
  an HTTP 401) and sends it as `Authorization: Bearer <token>` on every
  subsequent call.
- Endpoints, header contracts, and exact (Portuguese, accented) query
  parameter names for the two telemetric series endpoints
  (`HidroinfoanaSerieTelemetricaAdotada/v1` and `.../Detalhada/v1`) were
  locked by reading the live public OpenAPI document at
  `https://www.ana.gov.br/hidrowebservice/api-docs` (the Swagger UI itself is
  a client-rendered SPA that does not expose this via a simple fetch).
- **Response field names are NOT locked.** The OpenAPI document types the
  payload (`Devolucao.items`) as an opaque `object` with no published
  properties, and no credential was available to inspect a real response.
  The datasource therefore does not hardcode a wide-format column layout: it
  flattens whatever the API returns per record into snake_cased columns,
  plus request metadata (`station_id`, `variable`, `detail`, `chunk_start`,
  `chunk_end`) and a best-effort `timestamp` column detected by scanning key
  names. **Re-verify the column mapping against a live payload once the
  operator's ANA credentials exist.**
| `start_year` | integer | coleta | Initial year; `2003`+ (confirmed live) |
| `end_year` | integer | coleta | Final year (default: `start_year`) |
| `months` | string_list | coleta | Optional months `1`-`12`. Switches to the monthly product (`mensal/Brasil`, available from 2023 onward, own schema with `risco_fogo`/`frp`/`precipitacao`); `dataset` is ignored when set |
| `dataset` | string | coleta | `referencia_anual` (default, `Brasil_sat_ref`) or `todos_satelites` (`Brasil_todos_sats`); ignored when `months` is set |
| `states` | string_list | coleta | Optional post-download filter on the `estado` column (the downloaded file is always Brazil-wide); accepts UF codes or full names |
| `keep_raw` | boolean | tecnica | Save the raw ZIP/CSV bytes per file; default `false` |
| `timeout` | integer | tecnica | HTTP timeout in seconds (default `180`) |
| `api_base_url` | string | tecnica | Optional file-server base URL override |

INPE Queimadas notes:
- Annual output columns: `id_bdq, foco_id, lat, lon, data_pas, pais, estado,
  municipio, bioma` (plus `queimadas_produto` provenance). Monthly output
  columns differ: `id, lat, lon, data_hora_gmt, satelite, municipio, estado,
  pais, municipio_id, estado_id, pais_id, numero_dias_sem_chuva,
  precipitacao, risco_fogo, bioma, frp` — the monthly file is INPE's blended
  near-real-time product, not a finer-grained cut of the annual series.
  Requesting years+months outside 2023+ is skipped with a warning, not a
  failure.
- Complements — does not replace — `nasa_firms`: FIRMS is NASA's global
  near-real-time MODIS/VIIRS feed; INPE Queimadas is Brazil's own national
  program with its own satellite-reference methodology.
- No credential is required. Leaving `output_format` empty and
  `keep_raw=false` produces only a manifest and emits an `export_warning`.

### 3.23 CETESB QUALAR (`cetesb_qualar`, `cetesb_estacoes`)

Air quality for the state of São Paulo, from CETESB's public ArcGIS REST
service at `servicos.cetesb.sp.gov.br/arcgis` (verified live 2026-09-15). No
credential required. This is the first **state-level** publisher in the
catalogue; every other source is federal.

> **These are INDEX values, not concentrations.** The service publishes the
> CETESB/CONAMA air quality index, not µg/m³. The check that settles it: on
> 2026-09-15 10:00 the MP10 layer returned `M1 = 10` for the Americana station,
> and the station layer returned `Indice = 10` with `POLUENTE = MP10` for the
> same station and hour; it matched across eight stations. Concentration is
> only available through the classic QUALAR system, which requires a login.
> The index is a banded, non-linear transform and must not be fed to a
> dose-response model as though it were a concentration.

`cetesb_qualar` returns one row per station, pollutant and hour:
`estacao, municipio, latitude, longitude, poluente, datahora, indice`.
`cetesb_estacoes` returns the station registry, one row per station, with
address, municipality, coordinates and the current index.

| Parameter | Type | Phase | Notes |
| --- | --- | --- | --- |
| `pollutants` | string_list | coleta | `CO`, `MP10`, `MP2.5`, `NO2`, `O3`, `SO2`; omitted = all. Aliases `MP25`/`PM2.5`/`PM10` are accepted. `cetesb_qualar` only |
| `stations` | string_list | refinamento | Filter by station name, case-insensitive (e.g. `Cerqueira César`). `cetesb_qualar` only |
| `municipios` | string_list | refinamento | Filter by municipality; CETESB spells it upper-case and unaccented (`SAO PAULO`), but the comparison ignores case |
| `output_dir` | string | tecnica | Output folder, defaulting to `Guaraci Downloads` on the Desktop |
| `output_format` | string | exportacao | `csv`, `parquet`, `sqlite` |
| `keep_raw` | boolean | tecnica | Also keep the raw ArcGIS JSON; default `false` |
| `timeout` | integer | tecnica | HTTP timeout in seconds (default `120`) |
| `api_base_url` | string | tecnica | Optional MapServer base URL override |

CETESB notes:
- **Rolling 48-hour window, no history.** The service always returns the last
  48 hours and nothing more. Building a series means taking snapshots
  periodically and concatenating them. The bronze orchestrator does *not* do
  this: it is partitioned by year/month and models backfill, so both sources
  are marked `auto=False` and skipped by the sweep on purpose.
- **A frozen archive exists and is not used.** The `QA_Hist` service holds a
  table of 110,301 hourly rows, but it spans only 2021-03-02 to 2021-10-26 and
  stopped there. It is a dead snapshot, also in index units, not a series.
- **Municipality is joined at collection time.** The pollutant layers identify
  a station only by name and never say which municipality it sits in, and
  without that there is no link to the health data, which is indexed by
  municipality throughout Guaraci. The join against the station registry
  happens once, inside the connector. If the registry layer is unavailable the
  collection still completes, with `municipio` null and a warning.
- **Timestamps are local time.** `TM` fields are epoch milliseconds that decode
  to America/São_Paulo wall-clock time when read as UTC. Applying a timezone
  offset shifts the whole series by three hours and nothing fails loudly.
- **Index classification was reprocessed.** Since 2026-01-08 the classification
  follows CONAMA Resolution 506/2024, applied retroactively. Raw index values
  remain, but the quality bands are not comparable to what was published
  before that date.
- Scope is the state of São Paulo only, 62 stations.

### 3.24 CETESB QUALAR, measured concentration (`cetesb_qualar_horario`)

The counterpart to §3.23, and the one to use for exposure work. Where the open
ArcGIS gives an index for the last 48 hours, the classic QUALAR system gives
**measured concentration** over any historical range. It requires a free CETESB
account, created at `https://seguranca.cetesb.sp.gov.br/Home/CadastrarUsuario`.

| | `cetesb_qualar` | `cetesb_qualar_horario` |
| --- | --- | --- |
| Measure | index | concentration (µg/m³, ppm, …) |
| Range | last 48 h | any period |
| Credential | none | QUALAR account |
| Parameters | 6 pollutants | 12 pollutants + 8 meteorological |

Credentials are read **only** from `GUARACI_QUALAR_LOGIN` and
`GUARACI_QUALAR_SENHA`, never as job parameters, because job parameters are
persisted to the manifest and to the job history. This matches `nasa_firms`,
`nasa_gpm` and `ana_hidro`.

| Parameter | Type | Phase | Notes |
| --- | --- | --- | --- |
| `stations` | string_list | coleta | **Required.** Station name or QUALAR code. QUALAR answers one station per request, so there is no default |
| `parameters` | string_list | coleta | 12 pollutants (`MP10`, `MP2.5`, `O3`, `NO2`, `SO2`, `CO`, `NO`, `NOx`, `BEN`, `TOL`, `HCNM`, `ERT`) and 8 meteorological (`TEMP`, `UR`, `VV`, `DV`, `DVG`, `PRESS`, `RADG`, `RADUV`). Default: the six common pollutants |
| `start_date` / `end_date` | string | coleta | `YYYY-MM-DD` or `DD/MM/YYYY` |
| `only_validated` | boolean | refinamento | Default `true`: keep only readings CETESB marked as validated |
| `pause_seconds` | integer | tecnica | Delay between requests (default `1`) |
| `output_dir`, `output_format`, `keep_raw`, `timeout`, `api_base_url` | | | As in §3.23 |

Output columns: `estacao, codigo_estacao, latitude, longitude, parametro,
codigo_parametro, unidade, datahora, valor, validado`.

QUALAR notes:
- **One request per station per parameter.** There is no bulk call. Sweeping
  the whole network for six pollutants is 372 requests against a public state
  agency system, which is why `pause_seconds` exists and defaults to 1. The
  source is excluded from the bronze orchestrator sweep for the same reason.
- **The station code is not the ArcGIS `ID`.** Pinheiros is 99 in QUALAR and 42
  in the `cetesb_estacoes` layer. The two numberings happen not to overlap
  (ArcGIS uses 1-62, QUALAR 66-290, checked 2026-09-15), so a mix-up errors
  instead of silently returning another station. That is a property of the
  current data, not a guarantee, and there is a test pinning it.
- **A wrong password does not look like an error.** QUALAR answers HTTP 200
  with the login page, which would otherwise read as "no data in this period".
  The client detects this and raises.
- **Response is HTML, not CSV**, despite the endpoint being called
  `exportaDados`. Parsed with the standard library's `html.parser`, no new
  dependency.
- **Numbers are in Brazilian format** (`1.234,56`). The thousands separator is
  removed before the decimal comma is swapped; doing only the swap would turn
  `1.234,56` into `1.23456`.
- **A good login answers 302 with no `Location` header.** `urllib` cannot
  follow it and raises; the client reads any 3xx as a response, since the
  session cookie is already set. A wrong password still comes back as 200
  with the login page.
- **Status: validated live on 2026-09-24** (Pinheiros, MP10 and TEMP,
  2026-08-01 to 2026-08-07: 336 readings). The protocol was reconstructed
  from the system's own HTML and from the R package `qualR` (rOpenSci, MIT),
  which is also the source of the station and parameter code tables in
  `guaraci/cetesb/codes.py`.

### 3.25 ANVISA open-data files (`anvisa_*`)

Eight whole files from `https://dados.anvisa.gov.br/dados/`, a plain file
listing with no API (`/api` answers 404, verified live 2026-09-24). ANVISA
overwrites each file on update with no versioning, so history exists only if
the collector keeps copies; the orchestrator stores one snapshot per month.

| Source | File | Rows (2026-09-24) | Notes |
| --- | --- | --- | --- |
| `anvisa_vigimed_notificacoes` | `VigiMed_Notificacoes.csv` | 356 107 | pharmacovigilance notifications, patient data pseudonymised |
| `anvisa_vigimed_medicamentos` | `VigiMed_Medicamentos.csv` | 699 311 | drugs per notification, WHODrug and ATC |
| `anvisa_vigimed_reacoes` | `VigiMed_Reacoes.csv` | 1 093 739 | reactions in MedDRA, severity and outcome |
| `anvisa_tecnovigilancia` | `DADOS_ABERTOS_TECNOVIGILANCIA.csv` | 287 464 | medical devices, since 2012 |
| `anvisa_hemovigilancia` | `DADOS_ABERTOS_HEMOVIGILANCIA.csv` | 237 737 | transfusion reactions, since 2006 |
| `anvisa_medicamentos_registrados` | `DADOS_ABERTOS_MEDICAMENTOS.csv` | 43 557 | drug registrations |
| `anvisa_cmed_precos` | `TA_PRECO_MEDICAMENTO.csv` | 25 702 | CMED consumer price list |
| `anvisa_cmed_precos_governo` | `TA_PRECO_MEDICAMENTO_GOV.csv` | 25 702 | CMED government price (PMVG) |

| Parameter | Type | Phase | Notes |
| --- | --- | --- | --- |
| `output_format` | string | exportacao | `csv` (UTF-8), `parquet` or `sqlite`, every column as text; omit to keep the file as published (cp1252, `;`) |
| `keep_raw` | boolean | tecnica | Keep the published file next to the export, default `false` |
| `timeout` | integer | tecnica | HTTP timeout in seconds, default 600 (VigiMed files pass 100 MB) |
| `output_dir`, `api_base_url` | string | tecnica | Output folder; base URL override |

ANVISA notes:
- **Every column is exported as text.** Date formats change between files
  (MM/DD in VigiMed and hemovigilância, DD/MM in tecnovigilância) and
  `None` appears as a literal null; interpreting them belongs to the silver
  layer. Text also keeps leading zeros in registration numbers and EANs.
- **Download is skipped when the local copy has the size the server reports**
  in `Content-Length`; the payload carries `source_size` and
  `source_last_modified`.
- **Files without quoting are re-split line by line.** VigiMed does not quote
  fields, and a field starting with a quote (`"500" Dosage unit...`) made a
  CSV reader swallow the rest of the file. Tecnovigilância publishes
  `OCORRENCIA_NIVEL_1/2` as `" ; "`-separated lists without quotes (3 439
  rows with 2 to 8 extra fields); a `;` with a space on each side stays inside
  the field. A row that still does not fit (1 of 287 465, an unquoted `;` in
  the product name) is not cut by guess: it goes verbatim, with its line
  number, to `<source>.rejeitadas.csv`, reported in `rejected_rows` and in the
  warning. The orchestrator keeps that file next to the bronze CSV.
- **CMED opens with a legal preamble of variable length** (59 lines in one
  file, 72 in the other on 2026-09-24); the header row is found by content.
- **Left out on purpose:** `notivisa2_nsp_da.csv` (patient-safety adverse
  events, 1.3 GB) has no header row, and the dictionary ANVISA publishes for it
  describes a different table (an 11-field establishment registry, against 19
  event columns in the file), so any column name would be a guess. SNGPC
  (controlled-drug sales) is about 1 GB per month and is missing every month
  from 2021-11 to 2025-12.

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

