"""Spec-driven FTP backend shared by all phase-5 DATASUS systems.

One module serves SINASC, SIA, CNES, PNI, CIHA/CIH, SISCAN, SISPRENATAL,
RESP, PCE and the oncology panel — each is just a
:class:`~guaraci.datasus.ftp.specs.SystemSpec`. Mirrors the
``sih_backend``/``sim_backend`` contract (``discover_*_summary`` +
``download_*``) but takes the spec as its first argument instead of
hard-coding one system.

The download/decode/cache tail and the summary shaping are reused from
:mod:`guaraci.datasus.ftp.orchestration`; discovery from
:func:`guaraci.datasus.ftp.discovery.discover_spec`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from guaraci.datasus.ftp import dbc
from guaraci.datasus.ftp.catalog import FileRecord
from guaraci.datasus.ftp.client import DatasusFtpClient
from guaraci.datasus.ftp.discovery import (
    build_coverage_warning,
    discover_available_years,
    discover_spec,
)
from guaraci.datasus.ftp.orchestration import (
    ClientFactory,
    DbcReader,
    build_summary,
    download_records,
    run_coro,
)
from guaraci.datasus.ftp.specs import SystemSpec


def discover_summary(
    spec: SystemSpec,
    *,
    years: Sequence[int],
    groups: Optional[Sequence[str]] = None,
    states: Optional[Sequence[str]] = None,
    fetch_sizes: bool = True,
    client_factory: ClientFactory = DatasusFtpClient,
) -> Dict[str, Any]:
    """Preflight discovery payload for ``spec`` (no downloads)."""

    async def _impl() -> tuple[List[FileRecord], List[str]]:
        async with client_factory() as client:
            found = await discover_spec(
                client,
                spec,
                years=years,
                groups=groups,
                states=states,
                fetch_sizes=fetch_sizes,
            )
            if found:
                return found, []
            # Vazio pode ser ano fora da série publicada, o que é comum nos
            # sistemas descontinuados. Explica o motivo em vez de devolver um
            # zero indistinguível de falha.
            anos = await discover_available_years(client, spec, groups=groups)
            return found, [build_coverage_warning(spec.name, anos)]

    records, warnings = run_coro(_impl())

    year_list = sorted({int(y) for y in years})
    filters: Dict[str, Any] = {
        "start_year": year_list[0] if year_list else None,
        "end_year": year_list[-1] if year_list else None,
        "groups": list(groups) if groups else None,
    }
    if spec.has_state:
        filters["states"] = list(states) if states else None
    return build_summary(
        records, source=spec.name, filters=filters, warnings=warnings
    )


def download(
    spec: SystemSpec,
    *,
    years: Sequence[int],
    groups: Optional[Sequence[str]] = None,
    states: Optional[Sequence[str]] = None,
    cache_dir: Path,
    progress_callback: Optional[Any] = None,
    client_factory: ClientFactory = DatasusFtpClient,
    dbc_reader: DbcReader = dbc.read,
) -> Dict[str, Any]:
    """Discover, download, decode and persist a ``spec`` window as parquet.

    Returns ``{successful_downloads, failed_downloads, total_files,
    paths_by_group}`` — see
    :func:`guaraci.datasus.ftp.orchestration.download_records`.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    async def _impl() -> Dict[str, Any]:
        async with client_factory() as client:
            records = await discover_spec(
                client,
                spec,
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

    result: Dict[str, Any] = run_coro(_impl())
    return result
