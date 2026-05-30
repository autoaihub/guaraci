"""Filtered discovery of DATASUS files on the FTP server.

Replaces the in-line ``_discover_files`` block in
:mod:`guaraci.datasus.sih` with a source-agnostic primitive that the
phase-3 SIM/SINAN refactor can reuse.
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable, Iterable, Optional, Protocol, Sequence

from guaraci.datasus.ftp.catalog import (
    FileRecord,
    parse_sih,
    parse_sim,
    parse_sinan,
)

logger = logging.getLogger(__name__)


SIH_LEGACY_PATH: str = "/dissemin/publicos/SIHSUS/199201_200712/Dados"
SIH_CURRENT_PATH: str = "/dissemin/publicos/SIHSUS/200801_/Dados"

_SIH_WINDOW_BREAK_YEAR: int = 2008

# SIM splits its archive by classification directory.
SIM_CID10_PATH: str = "/dissemin/publicos/SIM/CID10/DORES"
SIM_CID9_PATH: str = "/dissemin/publicos/SIM/CID9/DORES"
_SIM_PATH_BY_GROUP: dict[str, str] = {
    "CID10": SIM_CID10_PATH,
    "CID9": SIM_CID9_PATH,
}

# SINAN keeps consolidated (FINAIS) and preliminary (PRELIM) national files.
SINAN_FINAIS_PATH: str = "/dissemin/publicos/SINAN/DADOS/FINAIS"
SINAN_PRELIM_PATH: str = "/dissemin/publicos/SINAN/DADOS/PRELIM"


class _FtpListing(Protocol):
    async def list_dir(self, path: str) -> Iterable: ...
    async def size(self, path: str) -> int: ...


async def discover_sih(
    client: _FtpListing,
    *,
    years: Sequence[int],
    groups: Optional[Sequence[str]] = None,
    states: Optional[Sequence[str]] = None,
    months: Optional[Sequence[int]] = None,
    fetch_sizes: bool = False,
) -> list[FileRecord]:
    """List SIH files matching the given filters.

    Traverses the legacy (1992–2007) and/or current (2008+) directories
    depending on the requested ``years``. Returns :class:`FileRecord`
    objects sorted by ``(group, state, year, month, basename)``.

    When ``fetch_sizes=True`` issues one extra ``SIZE`` call per matched
    file. Off by default to keep large discoveries cheap.
    """
    year_set = {int(y) for y in years}
    if not year_set:
        return []

    group_set = {g.upper() for g in groups} if groups else None
    state_set = {s.upper() for s in states} if states else None
    month_set = {int(m) for m in months} if months else None

    needs_legacy = any(y < _SIH_WINDOW_BREAK_YEAR for y in year_set)
    needs_current = any(y >= _SIH_WINDOW_BREAK_YEAR for y in year_set)

    discovered: list[FileRecord] = []
    if needs_legacy:
        discovered.extend(await _list_and_parse(client, SIH_LEGACY_PATH, parse_sih))
    if needs_current:
        discovered.extend(await _list_and_parse(client, SIH_CURRENT_PATH, parse_sih))

    filtered = [
        rec
        for rec in discovered
        if _matches(rec, year_set, group_set, state_set, month_set)
    ]

    if fetch_sizes:
        filtered = await _attach_sizes(client, filtered)

    filtered.sort(
        key=lambda r: (
            r.group,
            r.state or "",
            r.year,
            r.month or 0,
            r.basename,
        )
    )
    return filtered


async def discover_sim(
    client: _FtpListing,
    *,
    years: Sequence[int],
    groups: Optional[Sequence[str]] = None,
    states: Optional[Sequence[str]] = None,
    fetch_sizes: bool = False,
) -> list[FileRecord]:
    """List SIM files matching the given filters.

    SIM splits its archive by classification: CID-10
    (``DO<UF><YYYY>.dbc``, 1996+) under :data:`SIM_CID10_PATH` and CID-9
    (``MORT<UF><YYYY>.dbc``, 1979–1995) under :data:`SIM_CID9_PATH`. Only
    the directories for the requested ``groups`` are visited (both when
    ``groups`` is ``None``). Results are sorted by
    ``(group, state, year, basename)`` — SIM has no month dimension.
    """
    year_set = {int(y) for y in years}
    if not year_set:
        return []

    group_set = {g.upper() for g in groups} if groups else None
    state_set = {s.upper() for s in states} if states else None

    target_groups = sorted(group_set) if group_set else sorted(_SIM_PATH_BY_GROUP)
    discovered: list[FileRecord] = []
    for grp in target_groups:
        directory = _SIM_PATH_BY_GROUP.get(grp)
        if directory is None:
            logger.warning("Unknown SIM group %r; skipping", grp)
            continue
        discovered.extend(await _list_and_parse(client, directory, parse_sim))

    filtered = [
        rec
        for rec in discovered
        if _matches(rec, year_set, group_set, state_set, None)
    ]

    if fetch_sizes:
        filtered = await _attach_sizes(client, filtered)

    filtered.sort(key=lambda r: (r.group, r.state or "", r.year, r.basename))
    return filtered


async def discover_sinan(
    client: _FtpListing,
    *,
    years: Sequence[int],
    groups: Optional[Sequence[str]] = None,
    fetch_sizes: bool = False,
) -> list[FileRecord]:
    """List SINAN national files (``<DISEASE>BR<YY>.dbc``).

    Both the consolidated (:data:`SINAN_FINAIS_PATH`) and preliminary
    (:data:`SINAN_PRELIM_PATH`) directories are scanned — SINAN has no
    fixed year split between them. When the same basename exists in both,
    the ``FINAIS`` copy wins (``PRELIM`` only fills gaps, e.g. the most
    recent not-yet-consolidated year), which also keeps the download step
    idempotent. ``groups`` filters by disease code. Results are sorted by
    ``(group, year, basename)`` — SINAN national files have no state.
    """
    year_set = {int(y) for y in years}
    if not year_set:
        return []

    group_set = {g.upper() for g in groups} if groups else None

    finais = await _list_and_parse(client, SINAN_FINAIS_PATH, parse_sinan)
    prelim = await _list_and_parse(client, SINAN_PRELIM_PATH, parse_sinan)
    seen = {rec.basename for rec in finais}
    discovered = finais + [rec for rec in prelim if rec.basename not in seen]

    filtered = [
        rec
        for rec in discovered
        if _matches(rec, year_set, group_set, None, None)
    ]

    if fetch_sizes:
        filtered = await _attach_sizes(client, filtered)

    filtered.sort(key=lambda r: (r.group, r.year, r.basename))
    return filtered


async def discover_spec(
    client: _FtpListing,
    spec,
    *,
    years: Sequence[int],
    groups: Optional[Sequence[str]] = None,
    states: Optional[Sequence[str]] = None,
    fetch_sizes: bool = False,
) -> list[FileRecord]:
    """Generic discovery driven by a :class:`~guaraci.datasus.ftp.specs.SystemSpec`.

    Phase 5. Handles both layouts: ``spec.group_dirs`` (one directory per
    group — CNES, SISCAN; only the requested groups' dirs are listed) and
    ``spec.roots`` (flat directories whose files encode the group in the
    filename — SIA, SINASC, …). ``spec`` is duck-typed to avoid importing
    the specs module here.
    """
    year_set = {int(y) for y in years}
    if not year_set:
        return []

    group_set = {g.upper() for g in groups} if groups else None
    state_set = (
        {s.upper() for s in states} if (states and spec.has_state) else None
    )

    group_dirs = getattr(spec, "group_dirs", ()) or ()
    if group_dirs:
        directories = [
            d for g, d in group_dirs if group_set is None or g.upper() in group_set
        ]
    else:
        directories = list(spec.roots)

    discovered: list[FileRecord] = []
    for directory in directories:
        discovered.extend(await _list_and_parse(client, directory, spec.parse))

    filtered = [
        rec
        for rec in discovered
        if _matches(rec, year_set, group_set, state_set, None)
    ]

    if fetch_sizes:
        filtered = await _attach_sizes(client, filtered)

    filtered.sort(
        key=lambda r: (r.group, r.state or "", r.year, r.month or 0, r.basename)
    )
    return filtered


def _matches(
    rec: FileRecord,
    years: set[int],
    groups: Optional[set[str]],
    states: Optional[set[str]],
    months: Optional[set[int]],
) -> bool:
    if rec.year not in years:
        return False
    if groups is not None and rec.group not in groups:
        return False
    if states is not None and (rec.state or "") not in states:
        return False
    if months is not None and rec.month not in months:
        return False
    return True


async def _list_and_parse(
    client: _FtpListing,
    directory: str,
    parser: Callable[[str], Optional[FileRecord]],
) -> list[FileRecord]:
    entries = await client.list_dir(directory)
    records: list[FileRecord] = []
    for entry in entries:
        name = getattr(entry, "name", entry)
        record = parser(name)
        if record is None:
            continue
        records.append(record.with_path(f"{directory.rstrip('/')}/{record.basename}"))
    logger.debug("Discovered %d records in %s", len(records), directory)
    return records


async def _attach_sizes(
    client: _FtpListing,
    records: Sequence[FileRecord],
) -> list[FileRecord]:
    enriched: list[FileRecord] = []
    for rec in records:
        try:
            size = await client.size(rec.path)
        except Exception as exc:  # noqa: BLE001 — size is best-effort
            logger.warning("SIZE failed for %s: %s", rec.path, exc)
            size = 0
        enriched.append(rec.with_size(int(size)))
    return enriched
