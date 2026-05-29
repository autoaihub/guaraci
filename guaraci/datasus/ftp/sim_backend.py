"""High-level SIM orchestration over the direct FTP layer.

Phase 3 of ``docs/PLANO_DATASUS_FTP_DIRETO.md``. Mirrors
:mod:`guaraci.datasus.ftp.sih_backend` but for SIM, whose discovery has a
state dimension and no month dimension. The download/decode/cache tail is
shared via :mod:`guaraci.datasus.ftp.orchestration`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from guaraci.datasus.ftp import dbc
from guaraci.datasus.ftp.catalog import FileRecord
from guaraci.datasus.ftp.client import DatasusFtpClient
from guaraci.datasus.ftp.discovery import discover_sim as _discover_sim_async
from guaraci.datasus.ftp.orchestration import (
    ClientFactory,
    DbcReader,
    build_summary,
    download_records,
    run_coro,
)


def discover_sim_summary(
    *,
    years: Sequence[int],
    groups: Optional[Sequence[str]] = None,
    states: Optional[Sequence[str]] = None,
    fetch_sizes: bool = True,
    client_factory: ClientFactory = DatasusFtpClient,
) -> Dict[str, Any]:
    """Preflight SIM discovery payload (preflight, no downloads)."""

    async def _impl() -> List[FileRecord]:
        async with client_factory() as client:
            return await _discover_sim_async(
                client,
                years=years,
                groups=groups,
                states=states,
                fetch_sizes=fetch_sizes,
            )

    records: List[FileRecord] = run_coro(_impl())

    year_list = sorted({int(y) for y in years})
    return build_summary(
        records,
        source="sim",
        filters={
            "start_year": year_list[0] if year_list else None,
            "end_year": year_list[-1] if year_list else None,
            "groups": list(groups) if groups else None,
            "states": list(states) if states else None,
        },
    )


def download_sim(
    *,
    years: Sequence[int],
    groups: Sequence[str],
    states: Optional[Sequence[str]] = None,
    cache_dir: Path,
    progress_callback: Optional[Any] = None,
    client_factory: ClientFactory = DatasusFtpClient,
    dbc_reader: DbcReader = dbc.read,
) -> Dict[str, Any]:
    """Discover, download, decode and persist a SIM window as parquet.

    Returns ``{successful_downloads, failed_downloads, total_files,
    paths_by_group}``; see
    :func:`guaraci.datasus.ftp.orchestration.download_records`.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    async def _impl() -> Dict[str, Any]:
        async with client_factory() as client:
            records = await _discover_sim_async(
                client,
                years=years,
                groups=groups,
                states=states,
            )
            return await download_records(
                client,
                records,
                cache_dir=cache_dir,
                dbc_reader=dbc_reader,
                progress_callback=progress_callback,
            )

    return run_coro(_impl())
