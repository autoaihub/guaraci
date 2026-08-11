"""
Per-source samplers used to fill in the Guaraci data dictionary.

Each sampler takes a live DownloadService (or a gov.br DataSource class) and a
source key, makes the smallest safe real request it can, and returns a plain
dict shaped like a guaraci/data/field_dictionary.json entry:

    {"status": "ok", "rows_sampled": int, "fields": [str, ...]}
    {"status": "empty" | "error" | "needs_credential", "note": str}

Every sampler swallows its own exceptions — a single bad source must never
abort a batch run.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List, Literal

import polars as pl

# The 22 sources already covered by the original hand-picked DOWNLOAD_SAMPLES /
# DISCOVER_ONLY lists in scripts/sample_sources.py. Left untouched by this pass
# — they already carry real field names (or a deliberate discover-only status).
FTP_LEGACY_SOURCES = frozenset(
    {
        "sih", "sim", "sinan", "sinasc", "pni", "painel_oncologia", "dengue",
        "srag_demas", "doses_aplicadas_pni", "zikavirus", "chikungunya",
        "nasa_power", "nasa_firms", "nasa_gpm",
        "sia", "cnes", "ciha", "cih", "siscan", "sisprenatal", "resp", "pce",
    }
)

# Sources whose sole non-defaulted required parameter must be "seeded" from
# another source's sample (e.g. a CNES code). Deliberately out of scope for
# the automated pass: low reference value (unit lookups by ID, not bulk
# datasets) and they'd add a fragile inter-source dependency to the batch run.
SEEDED_SOURCES = frozenset(
    {
        "cnes_tipounidades_{codigo_tipo_unidade}",
        "cnes_estabelecimentos_{codigo_cnes}",
    }
)

GOVBR_SOURCES = frozenset({"snis", "sinisa"})

SourceCategory = Literal["ftp_legacy", "seeded", "govbr", "demas_generic"]


class RateLimited(Exception):
    """Raised instead of returning a dict entry, so the orchestrator's circuit
    breaker can count consecutive occurrences across sources without polluting
    the field dictionary with a non-standard status value."""


def classify_source(source: str) -> SourceCategory:
    if source in FTP_LEGACY_SOURCES:
        return "ftp_legacy"
    if source in SEEDED_SOURCES or "{" in source:
        return "seeded"
    if source in GOVBR_SOURCES:
        return "govbr"
    return "demas_generic"


def schema_of(svc: Any, source: str) -> Any:
    """Parameter names accepted by `source`, matching the plain string-list shape
    already stored in guaraci/data/field_dictionary.json and consumed by
    `guaraci fetch fields` (guaraci/cli/fetch_cli.py:309 does ", ".join(entry["filters"])
    — it must stay a list of strings, not the richer per-param objects)."""
    try:
        sch = svc.get_source_schema(source)
        return [p["name"] for p in sch["params"]]
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def _classify_exception(exc: Exception) -> str:
    msg = str(exc).lower()
    # Specific enough to not collide with unrelated errors that happen to contain
    # the word "token" (e.g. an HTML parser's "expected name token" message).
    if any(k in msg for k in ("map_key", "earthdata login", "guaraci_firms", "guaraci_earthdata")):
        return "needs_credential"
    return "error"


def _is_rate_limited(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(k in msg for k in ("429", "too many requests", "rate limit"))


def _clean_note(text: str, *, limit: int = 300) -> str:
    """Collapse whitespace/newlines so a note always renders as one Markdown bullet
    (some upstream error bodies are raw multi-line HTML, e.g. a 404 page)."""
    return " ".join(str(text).split())[:limit]


def sample_generic_demas(svc: Any, source: str, *, batch_size: int = 10, max_pages: int = 1) -> Dict[str, Any]:
    """Sample any auto-generated OpenDataSUS/DEMAS source with a tiny, generic window.

    Deliberately does not set uf/ano/etc: the schema scan already confirmed
    that (outside SEEDED_SOURCES) every DEMAS parameter is optional or has a
    default, so omitting them is safe (validate_source_params only rejects a
    missing value when required=True and default is None). batch_size x
    max_pages caps the volume regardless of how large the real dataset is.
    """
    try:
        with tempfile.TemporaryDirectory(prefix="guaraci_sample_") as tmp:
            res = svc.run(
                source,
                output_format="parquet",
                output_dir=tmp,
                batch_size=batch_size,
                max_pages=max_pages,
                keep_raw=False,
            )
            payload = res.to_dict() if hasattr(res, "to_dict") else dict(res)
            files = payload.get("exported_files") or []
            if not files:
                warning = payload.get("export_warning") or "no rows returned"
                return {"status": "empty", "note": _clean_note(warning)}
            df = pl.read_parquet(files[0])
            return {"status": "ok", "rows_sampled": df.height, "fields": df.columns}
    except RateLimited:
        raise
    except Exception as exc:  # noqa: BLE001
        if _is_rate_limited(exc):
            raise RateLimited(str(exc)) from exc
        return {"status": _classify_exception(exc), "note": _clean_note(exc)}


def _read_columns_any_format(path: Path) -> List[str]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        df = pl.read_csv(path, n_rows=5, infer_schema_length=5, truncate_ragged_lines=True)
        return df.columns
    if suffix in (".xlsx", ".xls"):
        df = pl.read_excel(path)
        return df.columns
    raise ValueError(f"unsupported sample file extension: {suffix}")


def sample_govbr_single_document(datasource_cls: Any, source: str, *, max_file_mb: int = 50) -> Dict[str, Any]:
    """Sample snis/sinisa by listing documents (no download) and fetching exactly one.

    Uses the public list_documents() plus the private _download_documents()
    (both defined on SinisaDataSource and inherited by SnisDataSource) to
    avoid pulling every published spreadsheet, which download() would do.
    """
    try:
        ds = datasource_cls()
        module = ds.VALID_MODULES[0]
        documents = ds.list_documents(file_kinds=["planilhas"], modules=[module])
        if not documents:
            return {"status": "empty", "note": f"no documents matched file_kinds=planilhas, module={module}"}
        with tempfile.TemporaryDirectory(prefix="guaraci_sample_") as tmp:
            raw_dir = Path(tmp) / "raw"
            raw_dir.mkdir(parents=True)
            state = ds._download_documents(  # noqa: SLF001 -- sampling-only, isolated here
                documents=[documents[0]],
                raw_dir=raw_dir,
                extracted_dir=None,
                extract_archives=False,
                overwrite=True,
                timeout=60,
            )
            if not state.downloaded:
                return {"status": "empty", "note": f"failed to fetch sample document: {state.failed}"}
            sample_path = Path(state.downloaded[0])
            if sample_path.stat().st_size > max_file_mb * 1024 * 1024:
                return {"status": "empty", "note": f"sample document exceeds {max_file_mb}MB, skipped"}
            fields = _read_columns_any_format(sample_path)
            return {"status": "ok", "rows_sampled": None, "fields": fields}
    except RateLimited:
        raise
    except Exception as exc:  # noqa: BLE001
        if _is_rate_limited(exc):
            raise RateLimited(str(exc)) from exc
        return {"status": _classify_exception(exc), "note": _clean_note(exc)}
