"""Shared synchronous orchestration for the direct-FTP backends.

SIH, SIM and SINAN differ only in *discovery* — which directories to
list, which catalog parser to apply, which filters are meaningful.
Everything downstream is identical:

- owning the asyncio loop so the public source API stays sync;
- downloading each ``.dbc``, decoding it to parquet, deleting the
  intermediate, and skipping files already cached (idempotency);
- shaping the discovery summary payload the API serialises to the UI.

That shared tail lives here so the three ``*_backend`` modules stay thin
(phase 3 of ``docs/PLANO_DATASUS_FTP_DIRETO.md``).
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from loguru import logger

from guaraci.datasus.ftp.catalog import FileRecord
from guaraci.datasus.ftp.client import DatasusFtpClient

ClientFactory = Callable[[], DatasusFtpClient]
DbcReader = Callable[[Path], Any]


def run_coro(coro: Any) -> Any:
    """Run an async coroutine even from inside a running event loop.

    Mirrors the pattern used by the legacy ``*DataSource.download`` methods
    so both backends behave the same when invoked from FastAPI handlers.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import nest_asyncio

        nest_asyncio.apply()
        return loop.run_until_complete(coro)
    return asyncio.run(coro)


def safe_unlink(path: Path) -> None:
    """Best-effort removal of a (possibly missing) file."""
    try:
        if path.exists():
            path.unlink()
    except OSError:  # pragma: no cover - best-effort cleanup
        pass


async def download_records(
    client: Any,
    records: Sequence[FileRecord],
    *,
    cache_dir: Path,
    dbc_reader: DbcReader,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Dict[str, Any]:
    """Download, decode and persist a list of :class:`FileRecord` as parquet.

    Files already converted to ``.parquet`` in ``cache_dir`` are reused
    instead of re-downloaded (idempotent). The intermediate ``.dbc`` is
    deleted after a successful decode. Per-file failures are recorded and
    do not abort the run.

    Returns ``{successful_downloads, failed_downloads, total_files,
    paths_by_group}``. ``paths_by_group`` lets each source populate
    ``self.data`` so ``load_dataframe`` keeps working unchanged.
    """
    total = len(records)
    if progress_callback is not None:
        progress_callback(0, total)

    successful = 0
    failed: List[Tuple[str, str]] = []
    paths_by_group: Dict[str, List[str]] = defaultdict(list)

    for index, record in enumerate(records, start=1):
        dbc_path = cache_dir / record.basename
        parquet_path = cache_dir / f"{Path(record.basename).stem}.parquet"
        try:
            if not parquet_path.exists():
                await client.download(record.path, dbc_path)
                df = dbc_reader(dbc_path)
                df.write_parquet(parquet_path)
                safe_unlink(dbc_path)
            paths_by_group[record.group].append(str(parquet_path))
            successful += 1
        except Exception as exc:  # noqa: BLE001 — caller wants partial success
            logger.error("FTP download failed for {}: {}", record.basename, exc)
            failed.append((record.group, record.basename))
            safe_unlink(dbc_path)
        finally:
            if progress_callback is not None:
                progress_callback(index, total)

    return {
        "successful_downloads": successful,
        "failed_downloads": failed,
        "total_files": total,
        "paths_by_group": dict(paths_by_group),
    }


def build_summary(
    records: Sequence[FileRecord],
    *,
    source: str,
    filters: Dict[str, Any],
    sample_limit: int = 10,
) -> Dict[str, Any]:
    """Shape a discovery payload identical to the legacy ``discover`` output.

    ``filters`` is passed in fully-formed by each backend, since the
    meaningful dimensions differ (SIH has months, SINAN has no states).
    """
    by_group: Dict[str, int] = defaultdict(int)
    by_state: Dict[str, int] = defaultdict(int)
    total_size = 0
    sample: List[Dict[str, Any]] = []
    for rec in records:
        by_group[rec.group] += 1
        if rec.state:
            by_state[rec.state] += 1
        total_size += int(rec.size or 0)
        if len(sample) < sample_limit:
            sample.append(
                {
                    "name": rec.basename,
                    "group": rec.group,
                    "state": rec.state,
                    "year": rec.year,
                    "month": rec.month,
                    "size_bytes": int(rec.size or 0),
                }
            )

    return {
        "source": source,
        "documents_found": len(records),
        "total_size_bytes": total_size,
        "by_group": dict(sorted(by_group.items())),
        "by_state": dict(sorted(by_state.items())),
        "sample": sample,
        "filters": filters,
    }
