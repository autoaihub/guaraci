"""High-level SINAN orchestration over the direct FTP layer.

Phase 3 of ``docs/PLANO_DATASUS_FTP_DIRETO.md``. Mirrors
:mod:`guaraci.datasus.ftp.sih_backend` but for SINAN, whose unit of
selection is the *disease* code (the catalog ``group``) and which has no
state or month dimension. The download/decode/cache tail is shared via
:mod:`guaraci.datasus.ftp.orchestration`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from guaraci.datasus.ftp import dbc
from guaraci.datasus.ftp.catalog import FileRecord
from guaraci.datasus.ftp.client import DatasusFtpClient
from guaraci.datasus.ftp.discovery import discover_sinan as _discover_sinan_async
from guaraci.datasus.ftp.orchestration import (
    ClientFactory,
    DbcReader,
    build_summary,
    download_records,
    run_coro,
)


def discover_sinan_summary(
    *,
    years: Sequence[int],
    diseases: Optional[Sequence[str]] = None,
    fetch_sizes: bool = True,
    client_factory: ClientFactory = DatasusFtpClient,
) -> Dict[str, Any]:
    """Preflight SINAN discovery payload (preflight, no downloads).

    ``diseases`` are the SINAN disease codes (e.g. ``DENG``), which map to
    the catalog ``group`` dimension.
    """

    async def _impl() -> List[FileRecord]:
        async with client_factory() as client:
            return await _discover_sinan_async(
                client,
                years=years,
                groups=diseases,
                fetch_sizes=fetch_sizes,
            )

    records: List[FileRecord] = run_coro(_impl())

    year_list = sorted({int(y) for y in years})
    return build_summary(
        records,
        source="sinan",
        filters={
            "start_year": year_list[0] if year_list else None,
            "end_year": year_list[-1] if year_list else None,
            "diseases": list(diseases) if diseases else None,
        },
    )


def download_sinan(
    *,
    years: Sequence[int],
    diseases: Sequence[str],
    cache_dir: Path,
    progress_callback: Optional[Any] = None,
    client_factory: ClientFactory = DatasusFtpClient,
    dbc_reader: DbcReader = dbc.read,
) -> Dict[str, Any]:
    """Discover, download, decode and persist SINAN files as parquet.

    Returns ``{successful_downloads, failed_downloads, total_files,
    paths_by_group}`` keyed by disease code; see
    :func:`guaraci.datasus.ftp.orchestration.download_records`.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    async def _impl() -> Dict[str, Any]:
        async with client_factory() as client:
            records = await _discover_sinan_async(
                client,
                years=years,
                groups=diseases,
            )
            return await download_records(
                client,
                records,
                cache_dir=cache_dir,
                dbc_reader=dbc_reader,
                progress_callback=progress_callback,
            )

    return run_coro(_impl())
