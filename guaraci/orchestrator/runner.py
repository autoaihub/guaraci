"""Execute fetch units into the bronze tree and emit ledger rows.

Two materialisation paths, chosen by source shape:

* **FTP batch** (``run_ftp_batch``): downloads a whole source's units over one
  connection, straight from each file's known path (no re-listing), reusing the
  idempotent parquet cache, then writes each *raw* file out as its own bronze
  CSV — 1 official DATASUS file = 1 CSV, at native granularity, with no UF
  remap (bronze stays the raw official content). Skips units already
  materialised and unchanged at source.
* **Service** (``run_via_service``): drives ``DownloadService.run`` for
  API-window (OpenDataSUS) and crawler (SNIS/SINISA) sources, then places the
  exported CSV in the bronze tree.

Both paths are dependency-injected (FTP client factory / the service), so the
orchestrator tests never touch the network.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from guaraci.orchestrator import paths
from guaraci.orchestrator.ledger import (
    STATUS_EMPTY,
    STATUS_ERROR,
    STATUS_OK,
    STATUS_PLANNED,
    STATUS_SKIPPED,
    Ledger,
    LedgerRow,
)
from guaraci.orchestrator.model import FetchUnit, Kind


# ---------------------------------------------------------------------------
# ledger-row helpers
# ---------------------------------------------------------------------------
def _base_row(unit: FetchUnit, run_id: str, ts: str, status: str, **extra: Any) -> LedgerRow:
    return LedgerRow(
        run_id=run_id,
        ts_utc=ts,
        source=unit.source,
        kind=unit.kind.value,
        granularity=unit.granularity.value,
        status=status,
        partition_key=unit.partition_key(),
        group=unit.group or "",
        state=unit.state or "",
        year=unit.year,
        month=unit.month,
        window_start=unit.start_date or "",
        window_end=unit.end_date or "",
        src_basename=unit.src_basename,
        src_size=unit.src_size,
        **extra,
    )


def _sanitize_key(unit: FetchUnit) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "_", unit.partition_key()).strip("_") or "unit"


# ---------------------------------------------------------------------------
# FTP batch path
# ---------------------------------------------------------------------------
class _Rec:
    """Minimal duck-typed FileRecord for ``download_records`` (path/basename/group)."""

    __slots__ = ("path", "basename", "group")

    def __init__(self, path: str, basename: str, group: str) -> None:
        self.path = path
        self.basename = basename
        self.group = group


def _cache_dir(bronze_root: Path) -> Path:
    override = os.environ.get("GUARACI_FTP_CACHE_DIR")
    path = Path(override) if override else Path(bronze_root) / ".cache_ftp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_ftp_batch(
    units: Sequence[FetchUnit],
    *,
    bronze_root: Path,
    run_id: str,
    ts: str,
    ledger: Ledger,
    dry_run: bool = False,
    tiers: Sequence[str] = ("raw", "refined"),
    cache_dir: Optional[Path] = None,
    client_factory: Optional[Callable[[], Any]] = None,
    dbc_reader: Optional[Callable[[Path], Any]] = None,
) -> List[LedgerRow]:
    """Materialise a batch of FTP units (all from the same source) as bronze CSVs.

    ``tiers`` selects the offerings: ``raw`` (the official file as-is) and/or
    ``refined`` (the same rows repartitioned by month, see ``refine.py``). Both
    are produced from a single decode of each file.
    """
    bronze_root = Path(bronze_root)
    tiers = tuple(tiers)
    index = ledger.index()
    rows: List[LedgerRow] = []
    todo: List[FetchUnit] = []

    for unit in units:
        raw_target = paths.bronze_path(bronze_root, unit, tier="raw")
        if dry_run:
            rows.append(_base_row(unit, run_id, ts, STATUS_PLANNED, out_path=str(raw_target)))
            continue
        # Skip only when the raw tier is requested and already present + unchanged;
        # a refined-only run always regenerates from the existing raw decode.
        if "raw" in tiers and raw_target.exists() and ledger.satisfied(unit, index=index):
            rows.append(_base_row(unit, run_id, ts, STATUS_SKIPPED, out_path=str(raw_target)))
            continue
        todo.append(unit)

    if dry_run or not todo:
        return rows

    import polars as pl
    from guaraci.datasus.ftp import dbc as dbc_module
    from guaraci.datasus.ftp.client import DatasusFtpClient
    from guaraci.datasus.ftp.orchestration import download_records, run_coro

    factory = client_factory or DatasusFtpClient
    reader = dbc_reader or dbc_module.read
    cache = Path(cache_dir) if cache_dir else _cache_dir(bronze_root)

    records = [_Rec(u.src_path, u.src_basename, u.group or "") for u in todo]

    async def _impl() -> Dict[str, Any]:
        async with factory() as client:
            return await download_records(
                client, records, cache_dir=cache, dbc_reader=reader
            )

    result = run_coro(_impl())
    failed = {basename for _group, basename in result.get("failed_downloads", [])}

    for unit in todo:
        if unit.src_basename in failed:
            rows.append(
                _base_row(unit, run_id, ts, STATUS_ERROR, error="download/decode failed")
            )
            continue
        parquet = cache / f"{Path(unit.src_basename).stem}.parquet"
        if not parquet.exists():
            rows.append(
                _base_row(unit, run_id, ts, STATUS_ERROR, error="parquet not produced")
            )
            continue
        try:
            frame = pl.read_parquet(parquet)
            out_path = ""
            n_bytes = 0
            refined_count = 0
            if "raw" in tiers:
                # Raw tier: the official file verbatim (no UF remap, no filtering,
                # no month split).
                target = paths.bronze_path(bronze_root, unit, tier="raw")
                target.parent.mkdir(parents=True, exist_ok=True)
                frame.write_csv(target)
                out_path = str(target)
                n_bytes = target.stat().st_size
            if "refined" in tiers:
                from guaraci.orchestrator.refine import write_refined

                refined_paths = write_refined(frame, unit, bronze_root)
                refined_count = len(refined_paths)
                if not out_path and refined_paths:
                    out_path = str(refined_paths[0])
            rows.append(
                _base_row(
                    unit,
                    run_id,
                    ts,
                    STATUS_OK,
                    documents_found=1,
                    downloaded_count=1,
                    refined_count=refined_count,
                    n_bytes=n_bytes,
                    out_path=out_path,
                )
            )
        except Exception as exc:  # noqa: BLE001 — per-file failure must not abort the batch
            rows.append(_base_row(unit, run_id, ts, STATUS_ERROR, error=str(exc)))

    return rows


# ---------------------------------------------------------------------------
# service path (API-window + crawler)
# ---------------------------------------------------------------------------
def _first_csv(exported: Sequence[str], search_dir: Path) -> Optional[Path]:
    for item in exported:
        candidate = Path(item)
        if candidate.suffix.lower() == ".csv" and candidate.exists():
            return candidate
    matches = sorted(search_dir.rglob("*.csv"))
    return matches[0] if matches else None


def run_via_service(
    unit: FetchUnit,
    *,
    service: Any,
    bronze_root: Path,
    run_id: str,
    ts: str,
    dry_run: bool = False,
) -> LedgerRow:
    """Materialise one API-window or crawler unit through ``DownloadService``."""
    bronze_root = Path(bronze_root)
    target = paths.bronze_path(bronze_root, unit)
    if dry_run:
        return _base_row(unit, run_id, ts, STATUS_PLANNED, out_path=str(target))

    try:
        schema = service.get_source_schema(unit.source)
        param_names = {p["name"] for p in schema.get("params", [])}
    except Exception as exc:  # noqa: BLE001
        return _base_row(unit, run_id, ts, STATUS_ERROR, error=f"schema: {exc}")

    kwargs: Dict[str, Any] = {}
    if unit.kind is Kind.API_WINDOW and unit.year is not None:
        if "start_year" in param_names:
            kwargs["start_year"] = unit.year
        if "end_year" in param_names:
            kwargs["end_year"] = unit.year

    if unit.kind is Kind.CRAWLER:
        out_dir = paths.crawler_dir(bronze_root, unit)
    else:
        out_dir = bronze_root / ".staging" / run_id / _sanitize_key(unit)
    out_dir.mkdir(parents=True, exist_ok=True)
    if "output_dir" in param_names:
        kwargs["output_dir"] = str(out_dir)
    if "output_format" in param_names:
        kwargs["output_format"] = "csv"

    try:
        result = service.run(unit.source, **kwargs)
        payload = result.to_dict() if hasattr(result, "to_dict") else dict(result)
    except Exception as exc:  # noqa: BLE001 — real runtime failure -> error row
        return _base_row(unit, run_id, ts, STATUS_ERROR, error=str(exc))

    documents = int(payload.get("documents_found", 0) or 0)
    downloaded = int(payload.get("downloaded_count", 0) or 0)

    # Crawlers write their own folder tree; record it as-is.
    if unit.kind is Kind.CRAWLER:
        status = STATUS_OK if documents or downloaded else STATUS_EMPTY
        return _base_row(
            unit,
            run_id,
            ts,
            status,
            documents_found=documents,
            downloaded_count=downloaded,
            out_path=str(out_dir),
        )

    exported = [str(p) for p in (payload.get("exported_files") or [])]
    produced = _first_csv(exported, out_dir)
    if produced is None:
        return _base_row(
            unit,
            run_id,
            ts,
            STATUS_EMPTY,
            documents_found=documents,
            downloaded_count=downloaded,
            error=str(payload.get("export_warning") or ""),
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    produced.replace(target)
    return _base_row(
        unit,
        run_id,
        ts,
        STATUS_OK,
        documents_found=documents,
        downloaded_count=downloaded,
        n_bytes=target.stat().st_size,
        out_path=str(target),
    )
