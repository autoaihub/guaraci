# *Data in Brief* — draft material by template section (Guaraci, v0.5.2)

> Platform-as-subject, English, comprehensive — **select and trim**. Each block names what the DiB
> template asks for, then gives draft content. Facts verified against the repository (see
> `guaraci-dossier.md`). Keep everything **descriptive** — DiB forbids conclusions/interpretation.
> Bracketed `[…]` items depend on the deposited data object (see §0).

---

## §0. Choose the data object first (everything below points to it)

DiB requires a dataset deposited with a DOI. For a platform-centred article, anchor to one of:

- **(D1)** a harmonized snapshot of one/few DATASUS systems over their full history, **or**
- **(D2)** a small **multi-source example collection** — one representative extract per acquisition
  mechanism (gov.br crawl, OpenDataSUS REST, DATASUS direct FTP, NASA point series) — plus the
  machine-readable **source catalog** and the per-run **manifests** Guaraci emits.

Deposit on **Zenodo or Mendeley Data**, license **CC BY 4.0**, including: the data files
(Parquet/CSV/SQLite), every `manifest.json`, a **data dictionary**, and a reuse README.
Fill the `[DOI]`/`[URL]` placeholders after deposit.

---

## §1. Article information

**Title** (must contain "data"/"dataset" — options):
- "Guaraci: a reproducible platform and dataset for direct acquisition of Brazilian public-health
  and environmental data"
- "A reproducible, multi-source dataset of Brazilian public health and environment assembled
  directly from primary sources with the Guaraci platform"
- "Open data acquisition from primary Brazilian sources: the Guaraci platform and a representative
  multi-source dataset"

**Authors** (confirm order; mark corresponding with *):
Luis Felipe Vogel Lopes*; Pedro Guilherme dos Reis Teixeira; Robson Parmezan Bonidia;
André Carlos Ponce de Leon Ferreira de Carvalho.

**Affiliations** (confirm full postal addresses):
- Instituto de Ciências Matemáticas e de Computação (ICMC), Universidade de São Paulo, São Carlos,
  SP, Brazil — Vogel Lopes, dos Reis Teixeira, de Carvalho.
- Universidade Tecnológica Federal do Paraná (UTFPR), Paraná, Brazil — Bonidia.

**Corresponding author email:** `vogel@usp.br`.

**Keywords** (4–8; do not repeat title words):
`Public health data; Brazil; DATASUS; Open government data; Data harmonization; Reproducible data
engineering; FAIR data; Environmental data`.

**Abstract** (100–500 words; data collection + dataset + reuse; no conclusions):
> Brazilian public data are dispersed across heterogeneous official systems — FTP servers
> (DATASUS), REST APIs (OpenDataSUS/DEMAS) and HTML portals (gov.br) — and published in legacy,
> often compressed formats (`.dbc`/`.dbf`) with schemas that change across years and topics, which
> makes integrated, reproducible reuse costly. This article describes **Guaraci**, an open-source
> (MIT), Docker-first platform that acquires such data **directly from the primary official
> sources**, decodes legacy formats, harmonizes heterogeneous schemas, and records full provenance,
> together with **[a representative dataset assembled with it]**. Guaraci integrates more than 80
> sources spanning public health (DATASUS microdata such as SIH, SIM, SINAN, SINASC, SIA, CNES,
> PNI; OpenDataSUS arbovirus and immunization data; gov.br sanitation indicators) and the
> environment (NASA POWER climate series, FIRMS active-fire detections, GPM IMERG precipitation),
> behind a single asynchronous job engine with a CLI, REST API and schema-driven UI. Data are
> decoded to records with `pyreaddbc`/`dbfread`, harmonized by taking the union of all historical
> columns (null-padding missing fields), and exported to CSV, Parquet and SQLite with a
> machine-readable `manifest.json` capturing source, request filters and output paths. The
> deposited dataset **[covers … for … ]** and is provided in **[formats]** with a data dictionary.
> By abstracting unstable FTP servers, paginated APIs and legacy encodings behind one reproducible
> interface, the dataset and platform lower the technical barrier to Brazilian public data and
> support spatio-temporal epidemiological analysis, machine learning, and cross-source studies.

## §2. Specifications table

| Field | Content |
|---|---|
| **Subject** | Health and Medical Sciences (select from dropdown; alt.: Computer Science → Information Systems). |
| **Specific subject area** (≤150 char) | Reproducible acquisition and harmonization of Brazilian public-health and environmental open data. |
| **Type of data** | Table; Raw and Processed/Harmonized. Formats: Parquet, CSV, SQLite; JSON manifest; data dictionary. |
| **Data collection** (≤600 char) | Data were collected programmatically from primary official sources with the open-source Guaraci platform (Python, Polars; Docker-first): DATASUS public FTP (`ftp.datasus.gov.br`, `.dbc`/`.dbf` microdata via `pyreaddbc`/`dbfread`), OpenDataSUS/DEMAS REST API, and gov.br portals (health); NASA POWER, FIRMS and GPM IMERG (environment). Files were downloaded directly, decoded, schema-harmonized (union of historical columns with null-padding) and exported; provenance was recorded per run in a manifest. |
| **Data source location** | Brazil (national; federative units / municipalities). Primary publishers: DATASUS, OpenDataSUS, gov.br (health); NASA POWER/FIRMS/GES DISC (environment). Processing institution: ICMC-USP, São Carlos, SP, Brazil. |
| **Data accessibility** | Repository: **[Zenodo/Mendeley Data]** · DOI: **[DOI]** · Direct URL: **[URL]** · Instructions: open Parquet/CSV/SQLite with standard tools; read `manifest.json` and the data dictionary for provenance and field definitions. Platform source code: https://github.com/autoaihub/guaraci (MIT). |
| **Related research article** | None. *(Or cite a Guaraci SoftwareX/JOSS software paper if submitted.)* |

## §3. Value of the data (3–6 bullets, ≤150 words each; no inferences)
- The data are acquired **directly from primary official publishers** (no third-party mirrors),
  preserving provenance and avoiding curation lag — each record's origin, request filters and
  collection are captured in a manifest.
- They remove a high technical barrier: DATASUS microdata ship as legacy `.dbc`/`.dbf` over
  unstable FTP servers; here they are decoded and exported to analysis-ready Parquet/CSV/SQLite.
- Heterogeneous historical schemas are **harmonized by column union with null-padding**, preserving
  every variable ever published across years and topics for longitudinal reuse.
- The collection is **reproducible**: a Docker-first runtime and an open platform let other
  researchers regenerate or extend the dataset with identical methodology.
- The dataset spans **both health and environment** (DATASUS/OpenDataSUS/gov.br and NASA),
  enabling spatio-temporal and machine-learning studies that link the two domains.
- It is directly relevant to under-resourced public-health research in the Global South, where
  data-engineering effort is often the main bottleneck.

## §4. Background (≤200 words; motivation/context; no conclusions)
Brazilian public data are published by different agencies through incompatible transports (FTP,
REST, HTML) and formats (compressed `.dbc`/`.dbf`, CSV, XLSX, JSON), with schemas that change
across years and topics and servers that are frequently unavailable. Assembling an integrated,
reproducible view therefore requires substantial, brittle extraction and ETL code. Guaraci was
developed within the AutoAI-Pandemics project (ICMC-USP) to provide a single, reproducible
acquisition layer that takes data **from the primary official sources**, decodes legacy formats and
harmonizes schemas, initially for the study of Neglected Tropical Diseases (SINAN) and later
generalized across public-health and environmental sources. The dataset described here was compiled
with that platform to make these sources reusable in analysis-ready formats with explicit
provenance.

## §5. Data description (describe the deposited dataset; tables/figures; no interpretation)
Describe exactly what is in the repository deposit:
- **Folder/file layout** — e.g., `raw/` (materialized source artifacts), `harmonized/…` (Parquet),
  `dictionary/data_dictionary.csv`, and one `manifest.json` per source/run.
- **Schema table (Table 1)** — one row per field: name, type, unit, source system, granularity.
  *(Essential — DiB expects a table that lets the reader follow the dataset structure.)*
- **Coverage table** — per source: system, period covered, geographic granularity (national / UF /
  municipality), row counts, file formats.
- **Provenance** — what each `manifest.json` records (source, request filters, materialized/exported
  paths, warnings, API params).
- **Suggested figures:** (Fig. 1) acquisition architecture — gov.br crawl / OpenDataSUS REST /
  DATASUS FTP / NASA → decode → harmonize → export; (Fig. 2) coverage timeline/map per source.
  *(The slide PNGs in `guaraci-apresentacao/img/` can serve as drafts, redrawn at high resolution.)*

## §6. Experimental design, materials and methods (no length limit — the technical core)
This is where **Guaraci is the instrument/method**. Suggested structure (full detail in
`guaraci-dossier.md` §4–§9):
- **6.1 Software and runtime.** Guaraci v0.5.2 (open-source, MIT; `github.com/autoaihub/guaraci`);
  Python 3.11/3.12; Polars/PyArrow/Pydantic v2/Click; Docker-first for reproducibility. Layered
  architecture: `datasources` → `DownloadService` (schema-validated registry) → `DownloadJobService`
  (asynchronous jobs, progress, retry, cancellation, disk persistence) → REST API / CLI / UI.
- **6.2 Acquisition by transport.** (i) gov.br HTML crawler (SNIS/SINISA); (ii) OpenDataSUS/DEMAS
  REST via an isolated HTTP client (native year filters; internal pagination; generated DEMAS
  sources from a Swagger catalog); (iii) **direct DATASUS FTP** (`ftplib` to `ftp.datasus.gov.br`;
  `.dbc`→`.dbf`→records via `pyreaddbc`/`dbfread`; plain `.dbf` for PNI; discovery preflight of
  volumetry before download), covering SIH/SIM/SINAN + 11 phase-5 systems; (iv) **NASA** POWER
  (keyless), FIRMS (CSV, 10-day chunks, MAP_KEY), GPM IMERG (GES DISC OPeNDAP point subsetting,
  Earthdata token) — all with no extra runtime dependency.
- **6.3 Decoding and harmonization.** `.dbc`/`.dbf` decoding to Polars; conservative **union** of
  all historical columns with null-padding; type standardization; **[for a linked dataset:
  municipality (IBGE) × month join]**.
- **6.4 Export and provenance.** CSV/Parquet/SQLite outputs + `manifest.json` (v1.1: source,
  filters, materialized/exported paths, warnings, API params). Collection is **idempotent** and
  delta-aware (re-fetches only new/changed files, judged by the volumetry preflight).
- **6.5 Reproducibility and integrity.** Docker-first execution; credentials supplied only via
  environment variables (`GUARACI_FIRMS_MAP_KEY`, `GUARACI_EARTHDATA_TOKEN`) and never persisted;
  automated test suite plus opt-in live smoke tests validating decoding against the real servers.
- **6.6 Reproduce this dataset.** Include the exact commands used, e.g.:
  `guaraci datasus discover sia 2024 2024 --groups PA` (preflight),
  `guaraci datasus download sinasc 2019 2020 --states SP --format parquet`, and the NASA/OpenDataSUS
  equivalents for the deposited extracts.

## §7. Limitations (≤200 words; collection/curation only)
Availability depends on the stability of external official servers (DATASUS FTP, government APIs),
which are intermittently unavailable; historical coverage windows differ by system. Bit-exact
parity between the new direct-FTP backend and the legacy PySUS path was not formally verified before
the default switch (the switch is reversible via one environment variable). Automated retry does not
yet use exponential backoff, and aggregate per-source observability is limited. The `nasa_gpm`
source is experimental and requires authorizing the GES DISC archive application. Source
notification data may carry under-reporting or data-entry lag at the origin, inherent to the
official source rather than to the processing described here.

## §8. Ethics statement
> The authors have read and follow the ethical requirements for publication in Data in Brief and
> confirm that the current work does not involve human subjects, animal experiments, or any data
> collected from social media platforms.

*(Confirm: all health microdata used are publicly released and de-identified at the source by
DATASUS/OpenDataSUS.)*

## §9. CRediT author statement (fill per contribution)
Example (adjust to reality):
- **Luis Felipe Vogel Lopes:** Conceptualization, Software, Data curation, Methodology,
  Writing – original draft.
- **Pedro Guilherme dos Reis Teixeira:** Software, Data curation, Validation.
- **Robson Parmezan Bonidia:** Conceptualization, Writing – review & editing.
- **André Carlos Ponce de Leon Ferreira de Carvalho:** Supervision, Funding acquisition,
  Writing – review & editing.

## §10. Acknowledgements (include funding in the funder's format)
> This work was developed within the AutoAI-Pandemics project (ICMC-USP), part of the AI4PEP
> network, with funding from the International Development Research Centre (IDRC), Canada
> **[grant ID — confirm]**.

## §11. Declaration of competing interests
> The authors declare that they have no known competing financial interests or personal
> relationships that could have appeared to influence the work reported in this paper.

## §12. References (≤20; numeric [n]; no irrelevant self-citation)
Candidate list (select ≤20):
1. DATASUS — Brazilian Ministry of Health, public microdata (`datasus.gov.br`).
2. OpenDataSUS / DEMAS open data portal.
3. SNIS/SINISA sanitation information systems (gov.br).
4. NASA POWER project.
5. NASA FIRMS active-fire information system.
6. NASA GPM IMERG (GES DISC).
7. `pyreaddbc` — DBC decoding.
8. `dbfread` — DBF reader.
9. Polars.
10. PyArrow.
11. FastAPI.
12. Pydantic.
13. Docker.
14. Wilkinson et al., The FAIR Guiding Principles for scientific data management and stewardship,
    *Sci. Data* 3 (2016) 160018.
15. Guaraci software citation (CITATION.cff; this release).
16. AI4PEP / IDRC programme reference.

*(If the data object is a climate–health linked dataset, add the most relevant epidemiological
references; keep ≤20 and avoid irrelevant self-citation.)*
