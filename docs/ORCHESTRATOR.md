# Bronze orchestrator (`guaraci orchestrate`)

The orchestrator sweeps **every** registered Guaraci source into a browsable
**bronze** tree of raw CSVs and keeps an append-only CSV **ledger** of everything
saved. It is the automation layer that runs on the server and feeds the Sabiá
data lake: a first full extraction ("sair tudo"), then periodic runs that add
only the delta.

> **Two tiers, both bronze.** The orchestrator offers `raw` (the official file
> as-is, native granularity) and `refined` (the same rows repartitioned into the
> browsable `disease/year/month` tree). `refined` is still *bronze* — a pure
> repartition of raw, with **no** column renaming, schema harmonisation, cross-
> source join or cleaning; that (silver) is downstream in the lake. See
> [Two tiers](#two-tiers-raw--refined).

## What "bronze" means here

One materialised CSV = one raw official source file, at the source's **native
granularity**, with no filtering, no UF remap and no month split:

| Source shape | Sources | Native unit | Bronze granularity |
| --- | --- | --- | --- |
| Per disease, annual | `sinan` | 1 file / disease / year | annual |
| Per UF, annual | `sim`, `sinasc`, … | 1 file / UF / year | annual |
| Per UF, monthly | `sih`, `sia`, `cnes`, … | 1 file / UF / competência | monthly |
| Date window (API) | OpenDataSUS | 1 slice / year | annual |
| Point (API) | NASA | needs lat/lon | **on demand** (not swept) |
| Portal crawl | `snis`, `sinisa` | whole portal | folder |

The current-year file (e.g. SINAN preliminary) grows over the year; the updater
notices via the recorded source size and re-pulls it.

## Two tiers (raw + refined)

Both are written from a single decode of each file, under sibling roots:

- **`raw/`** — the official file verbatim, at native granularity. 1 DATASUS file
  = 1 CSV. No UF remap, no filtering, no month split. Auditable 1:1 (keeps the
  official basename).
- **`refined/`** — the *same rows* repartitioned into the uniform
  `<source>/<group>/<state>/<year>/<month>` tree the front-end browses. Monthly
  sources pass through at their competência; annual sources (SINAN/SIM/SINASC)
  are split by their event date (`DT_NOTIFIC`/`DTOBITO`/`DTNASC`). The month is
  derived using the file's own year as an oracle (format-agnostic); a row whose
  date can't be placed lands in an `00` (unknown) bucket — never mis-bucketed,
  never dropped. Still bronze: no harmonisation.

Pick tiers with `--tier raw|refined|both` (default `both`).

## Bronze tree layout

```
<bronze_root>/
  _ledger.csv                                  # the log (state + public manifest)
  raw/                                         # tier 1: official file as-is
    SINAN/DENG/2024/DENGBR24.csv               #   per disease, annual
    SIM/CID10/SP/2020/DOSP2020.csv             #   per UF, annual
    SIH/RD/PR/2024/01/RDPR2401.csv             #   per UF, monthly
    DENGUE/2023/dengue_2023.csv                #   OpenDataSUS, per year
  refined/                                     # tier 2: repartitioned by month
    SINAN/DENG/2024/03/DENGBR24-202403.csv     #   SINAN split by DT_NOTIFIC
    SINAN/DENG/2024/00/DENGBR24-202400.csv     #   unknown-month bucket
    SIH/RD/PR/2024/01/RDPR2401-202401.csv      #   monthly passthrough
  _logs/orchestrate-YYYYMMDD.log               # server wrapper logs
```

Refined currently covers the DATASUS FTP sources (the microdata the front-end
navigates); OpenDataSUS/NASA/crawler sources are raw-only for now.

## The ledger (`_ledger.csv`)

Append-only; one row per partition attempt. Columns: `run_id, ts_utc, source,
kind, granularity, group, state, year, month, window_start, window_end, status,
documents_found, downloaded_count, n_bytes, src_basename, src_size, out_path,
error, partition_key`.

- **State** the updater reads to fetch only the next / changed partition
  ("bater volumetria": `src_size` detects a grown current-year file).
- **Public manifest** the FTP/web front-end can read to show what exists.
- Statuses: `ok`, `empty` (re-checked next run), `error`, `skipped`
  (idempotent no-op), `planned` (dry-run).

## CLI

```bash
# Resolved profile (kind / cadence / backfill floor) per source — offline
guaraci orchestrate profiles [-s sih -s sim ...]

# Dry-run: contact the source and list what WOULD be fetched (no download)
guaraci orchestrate plan [-s sinan] [--update]

# Full history into the bronze tree ("sair tudo")
guaraci orchestrate backfill [-s sinan -s sim -s sih] [--tier both] [-o /data/bronze]

# Incremental: pull only the delta the ledger doesn't have yet
guaraci orchestrate update [-s sih] [--tier both] [-o /data/bronze]

# Read the ledger: materialised partitions per source + last activity
guaraci orchestrate status [-o /data/bronze]
```

The bronze root comes from `-o/--bronze-root` or `$GUARACI_BRONZE_ROOT`
(default `./bronze`). `--dry-run` is available on `backfill`/`update`.

## Per-source cadence (config de cadência)

Each source resolves to a `SourceProfile` (`guaraci/orchestrator/cadence.py`)
with a publication **cadence** (`daily`/`weekly`/`monthly`/`annual`/`irregular`)
so the updater re-checks on the right rhythm instead of a single fixed sweep.
Re-tune a source's cadence in `CADENCE_OVERRIDES`; NASA sources are `auto=False`
(collected on demand because they need a latitude/longitude).

## Running on the server

Thin cron/scheduler entrypoints live in `scripts/server/` (a lock prevents
overlapping runs; output goes to `<bronze_root>/_logs/`):

```bash
# Linux (e.g. the Sabiá host) — first full extraction once, then daily deltas:
GUARACI_BRONZE_ROOT=/data/bronze GUARACI_ORCH_MODE=backfill scripts/server/orchestrate.sh
# crontab: 0 3 * * *  GUARACI_BRONZE_ROOT=/data/bronze /opt/guaraci/scripts/server/orchestrate.sh
```

```powershell
# Windows console:
./scripts/server/orchestrate.ps1 -BronzeRoot D:\bronze -Mode backfill   # first run
./scripts/server/orchestrate.ps1 -BronzeRoot D:\bronze                   # incremental
```

Tunable via env: `GUARACI_BRONZE_ROOT`, `GUARACI_PYTHON`, `GUARACI_ORCH_MODE`
(`update`|`backfill`), `GUARACI_ORCH_ARGS` (extra args, e.g. `-s sih -s sim`).

## Decisions

- **A — raw vs processed view — RESOLVED (2026-07-13):** offer **both**, as two
  bronze tiers (`raw` + `refined`), not silver. Implemented (see
  [Two tiers](#two-tiers-raw--refined)).
- **C — IBGE — DONE (2026-07-14):** three SIDRA sources registered and swept as
  annual `api_window`s — `ibge_populacao` (estimates, table 6579, from 2001),
  `ibge_pib_municipios` (municipal GDP, table 5938, from 2002) and
  `ibge_populacao_idade_sexo` (census population by sex/age, table 9514, 2022).
  All validated live. Further IBGE datasets can follow the same
  `SidraAggregateSource` pattern on request.

## Notes / follow-ups

- **Backfill cost**: `backfill` for a large monthly source is a big one-time
  download; run it once, by hand, off-peak. `update` is small.
- Generic monthly FTP systems (SIA/CNES) currently download a whole year per
  group/UF; per-month bronze splitting for those is a possible refinement.
- The orchestrator reuses `DownloadService` + the verified FTP discovery/cache
  primitives; it does not reimplement collection.
