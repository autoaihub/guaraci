"""High-level SIH orchestration over the direct FTP layer.

Bridge between the public contract of :class:`guaraci.datasus.sih.SihDataSource`
and the primitives in :mod:`guaraci.datasus.ftp.client`,
:mod:`guaraci.datasus.ftp.discovery` and :mod:`guaraci.datasus.ftp.dbc`.

Both entry points are **sync** — they own the asyncio loop internally, so
they can be called from the existing sync API of ``SihDataSource``
without leaking ``async`` into the caller.

Layout:

- :func:`discover_sih_summary` mirrors :meth:`SihDataSource.discover`
  (preflight, no downloads).
- :func:`download_sih`         mirrors :meth:`SihDataSource.download`
  (discover → download .dbc → decode → write .parquet).

Both accept injectable ``client_factory`` and ``dbc_reader`` so tests can
exercise the wiring without touching the network.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from loguru import logger

from guaraci.datasus.ftp import dbc
from guaraci.datasus.ftp.catalog import FileRecord
from guaraci.datasus.ftp.client import DatasusFtpClient
from guaraci.datasus.ftp.discovery import discover_sih as _discover_sih_async

ClientFactory = Callable[[], DatasusFtpClient]
DbcReader = Callable[[Path], Any]


def _run_coro(coro: Any) -> Any:
    """Run an async coroutine even when called from inside a running event loop.

    Mirrors the pattern already used by :meth:`SihDataSource.download` so
    both backends behave the same when invoked from FastAPI handlers.
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


def discover_sih_summary(
    *,
    years: Sequence[int],
    groups: Optional[Sequence[str]] = None,
    states: Optional[Sequence[str]] = None,
    months: Optional[Sequence[int]] = None,
    fetch_sizes: bool = True,
    client_factory: ClientFactory = DatasusFtpClient,
) -> Dict[str, Any]:
    """Preflight discovery payload, shaped like :meth:`SihDataSource.discover`.

    Connects, lists, optionally fetches ``SIZE`` for each match, and
    returns the canonical summary the API serializes back to the UI.
    """

    async def _impl() -> List[FileRecord]:
        async with client_factory() as client:
            return await _discover_sih_async(
                client,
                years=years,
                groups=groups,
                states=states,
                months=months,
                fetch_sizes=fetch_sizes,
            )

    records: List[FileRecord] = _run_coro(_impl())

    by_group: Dict[str, int] = defaultdict(int)
    by_state: Dict[str, int] = defaultdict(int)
    total_size = 0
    sample: List[Dict[str, Any]] = []
    for rec in records:
        by_group[rec.group] += 1
        if rec.state:
            by_state[rec.state] += 1
        total_size += int(rec.size or 0)
        if len(sample) < 10:
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

    year_list = sorted({int(y) for y in years})
    return {
        "source": "sih",
        "documents_found": len(records),
        "total_size_bytes": total_size,
        "by_group": dict(sorted(by_group.items())),
        "by_state": dict(sorted(by_state.items())),
        "sample": sample,
        "filters": {
            "start_year": year_list[0] if year_list else None,
            "end_year": year_list[-1] if year_list else None,
            "groups": list(groups) if groups else None,
            "states": list(states) if states else None,
            "months": list(months) if months else None,
        },
    }


def download_sih(
    *,
    years: Sequence[int],
    groups: Sequence[str],
    states: Optional[Sequence[str]] = None,
    months: Optional[Sequence[int]] = None,
    cache_dir: Path,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    client_factory: ClientFactory = DatasusFtpClient,
    dbc_reader: DbcReader = dbc.read,
) -> Dict[str, Any]:
    """Discover, download, decode and persist a SIH window as parquet.

    Files already converted to ``.parquet`` in ``cache_dir`` are reused
    instead of being re-downloaded (idempotent). The intermediate
    ``.dbc`` is deleted after a successful decode.

    Returns ``{successful_downloads, failed_downloads, total_files,
    paths_by_group}``. The last key lets :class:`SihDataSource` populate
    ``self.data`` so :meth:`SihDataSource.load_dataframe` keeps working.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    async def _impl() -> Dict[str, Any]:
        async with client_factory() as client:
            records = await _discover_sih_async(
                client,
                years=years,
                groups=groups,
                states=states,
                months=months,
            )

            total = len(records)
            if progress_callback is not None:
                progress_callback(0, total)

            successful = 0
            failed: List[tuple[str, str]] = []
            paths_by_group: Dict[str, List[str]] = defaultdict(list)

            for index, record in enumerate(records, start=1):
                dbc_path = cache_dir / record.basename
                parquet_path = cache_dir / f"{Path(record.basename).stem}.parquet"
                try:
                    if not parquet_path.exists():
                        await client.download(record.path, dbc_path)
                        df = dbc_reader(dbc_path)
                        df.write_parquet(parquet_path)
                        _safe_unlink(dbc_path)
                    paths_by_group[record.group].append(str(parquet_path))
                    successful += 1
                except Exception as exc:  # noqa: BLE001 — caller wants partial success
                    logger.error("FTP SIH failed for %s: %s", record.basename, exc)
                    failed.append((record.group, record.basename))
                    _safe_unlink(dbc_path)
                finally:
                    if progress_callback is not None:
                        progress_callback(index, total)

            return {
                "successful_downloads": successful,
                "failed_downloads": failed,
                "total_files": total,
                "paths_by_group": dict(paths_by_group),
            }

    return _run_coro(_impl())


def _safe_unlink(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError:  # pragma: no cover - best-effort cleanup
        pass
