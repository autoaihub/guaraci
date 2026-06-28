"""Sample each first-class Guaraci source to validate it works and capture its
filter parameters + output field names — a data dictionary for data-lake consumers.

This is the empirical "run it once, broadly" applied to Guaraci's real mission
(feeding the data lake from many sources). It is a long/verbose live job, so per
the Vogel Stack (operação §5.1) run it with a persisted log:

    .venv/Scripts/python.exe scripts/sample_sources.py

Writes (incrementally, so a partial run still yields data):
  reports/source_validation.json   — machine-readable per-source status/filters/fields
  reports/data_dictionary.md       — human-readable filters + field names per source

Windows are intentionally tiny (AC = smallest UF, 1 month/year). NASA FIRMS/GPM
need credentials (env vars); without them they are reported as needs_credential.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import polars as pl

from guaraci.services.downloads import DownloadService

OUT_DIR = Path("reports")
OUT_DIR.mkdir(exist_ok=True)
JSON_OUT = OUT_DIR / "source_validation.json"
MD_OUT = OUT_DIR / "data_dictionary.md"

svc = DownloadService()

# Real download (captures output field names). Smallest feasible windows.
DOWNLOAD_SAMPLES = {
    "sih": dict(start_year=2024, end_year=2024, groups=["RD"], states=["AC"], months=["1"]),
    "sim": dict(start_year=2021, end_year=2021, groups=["CID10"], states=["AC"]),
    "sinan": dict(start_year=2022, end_year=2022, diseases=["ZIKA"]),
    "sinasc": dict(start_year=2021, end_year=2021, states=["AC"]),
    "pni": dict(start_year=2021, end_year=2021, states=["AC"]),
    "painel_oncologia": dict(start_year=2023, end_year=2023),
    "dengue": dict(start_year=2024, end_year=2024, uf="AC", max_pages=1),
    "srag_demas": dict(start_year=2023, end_year=2023, uf="AC", max_pages=1),
    "doses_aplicadas_pni": dict(start_year=2023, end_year=2023, uf="AC", max_pages=1),
    "zikavirus": dict(start_year=2022, end_year=2022, uf="AC", max_pages=1),
    "chikungunya": dict(start_year=2024, end_year=2024, uf="AC", max_pages=1),
    "nasa_power": dict(latitude="-23.55", longitude="-46.63", start_date="2024-01-01", end_date="2024-01-07"),
    "nasa_firms": dict(start_date="2024-01-01", end_date="2024-01-02", country="BRA"),
    "nasa_gpm": dict(latitude="-23.55", longitude="-46.63", start_date="2024-01-01", end_date="2024-01-02"),
}

# FTP systems validated via discover (preflight, no download) — heavy to pull fully.
DISCOVER_ONLY = {
    "sia": dict(start_year=2023, end_year=2023, states=["AC"]),
    "cnes": dict(start_year=2024, end_year=2024, states=["AC"]),
    "ciha": dict(start_year=2014, end_year=2014, states=["AC"]),
    "cih": dict(start_year=2009, end_year=2009, states=["AC"]),
    "siscan": dict(start_year=2019, end_year=2019, states=["AC"]),
    "sisprenatal": dict(start_year=2014, end_year=2014, states=["AC"]),
    "resp": dict(start_year=2016, end_year=2016),
    "pce": dict(start_year=2014, end_year=2014),
}


def log(msg: str) -> None:
    print(msg, flush=True)


def schema_of(source: str):
    try:
        sch = svc.get_source_schema(source)
        return [
            {"name": p["name"], "type": p["type"], "required": p.get("required"),
             "allowed": p.get("allowed_values")}
            for p in sch["params"]
        ]
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


results: dict = {}


def write_partial() -> None:
    JSON_OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")


# 1) Filter schema for ALL registered sources (instant, no network).
all_sources = [d.source for d in svc.list_sources()]
log(f"[schema] {len(all_sources)} sources")
for s in all_sources:
    results.setdefault(s, {})["filters"] = schema_of(s)
write_partial()

# 2) Discover (preflight) for the heavier FTP systems.
for s, params in DISCOVER_ONLY.items():
    log(f"[discover] {s} {params}")
    try:
        summ = svc.discover(s, fetch_sizes=False, **params)
        results.setdefault(s, {})["discover"] = {
            "status": "ok",
            "documents_found": summ.get("documents_found"),
            "by_group": summ.get("by_group"),
            "by_state": summ.get("by_state"),
        }
        log(f"   -> ok: {summ.get('documents_found')} files")
    except Exception as exc:  # noqa: BLE001
        results.setdefault(s, {})["discover"] = {"status": "error", "error": str(exc)[:300]}
        log(f"   -> error: {str(exc)[:160]}")
    write_partial()

# 3) Download a small sample to capture output field names.
for s, params in DOWNLOAD_SAMPLES.items():
    log(f"[sample] {s} {params}")
    rec = results.setdefault(s, {})
    try:
        with tempfile.TemporaryDirectory(prefix="guaraci_sample_") as tmp:
            res = svc.run(s, output_format="parquet", output_dir=tmp, **params)
            payload = res.to_dict() if hasattr(res, "to_dict") else dict(res)
            files = payload.get("exported_files") or []
            if files:
                df = pl.read_parquet(files[0])
                rec["sample"] = {"status": "ok", "rows": df.height,
                                 "n_cols": df.width, "columns": df.columns}
                log(f"   -> ok: {df.height} rows, {df.width} cols")
            else:
                rec["sample"] = {"status": "empty", "warning": payload.get("export_warning")}
                log(f"   -> empty: {payload.get('export_warning')}")
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        low = msg.lower()
        status = "needs_credential" if any(k in low for k in ("map_key", "token", "earthdata")) else "error"
        rec["sample"] = {"status": status, "error": msg[:300]}
        log(f"   -> {status}: {msg[:160]}")
    write_partial()

# 4) Human-readable data dictionary.
lines = [
    "# Data dictionary — amostragem por fonte\n\n",
    f"Gerado por `scripts/sample_sources.py`. {len(all_sources)} fontes registradas.\n",
    "Filtros = argumentos que o usuário pode passar; Campos = colunas de saída (amostra real).\n",
]
for s in sorted(results):
    rec = results[s]
    lines.append(f"\n## {s}\n\n")
    filt = rec.get("filters")
    if isinstance(filt, list):
        rendered = ", ".join(
            f"`{p['name']}`({p['type']}{'*' if p.get('required') else ''})" for p in filt
        )
        lines.append(f"- **Filtros:** {rendered}\n")
    if "discover" in rec:
        d = rec["discover"]
        lines.append(f"- **Discover:** {d.get('status')} — {d.get('documents_found')} arquivo(s); by_group={d.get('by_group')}\n")
    if "sample" in rec:
        sp = rec["sample"]
        if sp.get("status") == "ok":
            lines.append(f"- **Amostra:** OK — {sp['rows']} linhas, {sp['n_cols']} colunas\n")
            lines.append("- **Campos:** " + ", ".join(f"`{c}`" for c in sp["columns"]) + "\n")
        else:
            lines.append(f"- **Amostra:** {sp.get('status')} — {sp.get('error') or sp.get('warning')}\n")
MD_OUT.write_text("".join(lines), encoding="utf-8")
log(f"\nDONE. JSON: {JSON_OUT}  MD: {MD_OUT}")
