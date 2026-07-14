"""Enumerate the fetch units for a source — the "what to pull" step.

``plan_backfill`` produces the full history ("sair tudo"); ``plan_update``
produces just the delta the ledger doesn't already have (the monthly/periodic
run). Both are pure given a records provider, so they unit-test without a
network — the default provider is the only thing that touches the FTP server.

Per source shape:

* **FTP** (SINAN/SIM/SIH + spec systems): one unit per *actual* DATASUS file,
  discovered at file granularity. Native granularity is preserved — a monthly
  file yields a monthly unit, an annual file an annual unit.
* **API-window** (OpenDataSUS): one unit per year (backfill floor is a bounded
  heuristic; DATASUS microdata is the priority surface).
* **NASA / unknown**: skipped by the sweep (NASA needs a lat/lon → on demand).
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable, List, Optional, Sequence

from guaraci.orchestrator.cadence import SourceProfile
from guaraci.orchestrator.ledger import Ledger
from guaraci.orchestrator.model import FetchUnit, Kind

# Provider signature: (kind, source, years) -> list of FileRecord-like objects
# (duck-typed: .group .state .year .month .basename .path .size).
FtpRecordsProvider = Callable[[Kind, str, Sequence[int]], List[object]]

# Bounded default backfill window for API-window sources (years). DATASUS FTP is
# the priority; OpenDataSUS floors can be widened per source when needed.
_API_BACKFILL_YEARS = 5


def _now_year() -> int:
    return datetime.now().year


def default_ftp_records(
    kind: Kind, source: str, years: Sequence[int]
) -> List[object]:
    """Live file-level discovery against the DATASUS FTP server.

    Reuses the verified phase-3/phase-5 discovery primitives and owns the async
    loop through ``run_coro`` so the planner stays synchronous.
    """
    from guaraci.datasus.ftp.client import DatasusFtpClient
    from guaraci.datasus.ftp.discovery import (
        discover_sih,
        discover_sim,
        discover_sinan,
        discover_spec,
    )
    from guaraci.datasus.ftp.orchestration import run_coro
    from guaraci.datasus.ftp.specs import get_spec

    async def _impl() -> List[object]:
        async with DatasusFtpClient() as client:
            if kind is Kind.FTP_SIH:
                return list(await discover_sih(client, years=years))
            if kind is Kind.FTP_SIM:
                return list(await discover_sim(client, years=years))
            if kind is Kind.FTP_SINAN:
                return list(await discover_sinan(client, years=years))
            spec = get_spec(source)
            return list(await discover_spec(client, spec, years=years))

    return run_coro(_impl())


def _record_to_unit(source: str, kind: Kind, rec: object) -> FetchUnit:
    """Map a discovered ``FileRecord`` to a :class:`FetchUnit`.

    SINAN national files carry the disease in ``group`` and have no state; every
    other FTP shape carries group/state and (for monthly systems) a month.
    """
    state = None if kind is Kind.FTP_SINAN else getattr(rec, "state", None)
    month = None if kind is Kind.FTP_SINAN else getattr(rec, "month", None)
    return FetchUnit(
        source=source,
        kind=kind,
        group=getattr(rec, "group", None),
        state=state,
        year=int(getattr(rec, "year")),
        month=int(month) if month is not None else None,
        src_basename=getattr(rec, "basename", "") or "",
        src_path=getattr(rec, "path", "") or "",
        src_size=int(getattr(rec, "size", 0) or 0),
    )


def _ftp_units(
    profile: SourceProfile,
    years: Sequence[int],
    records_provider: FtpRecordsProvider,
) -> List[FetchUnit]:
    records = records_provider(profile.kind, profile.source, list(years))
    return [_record_to_unit(profile.source, profile.kind, rec) for rec in records]


def _api_window_units(source: str, years: Sequence[int]) -> List[FetchUnit]:
    return [
        FetchUnit(source=source, kind=Kind.API_WINDOW, year=int(y)) for y in years
    ]


def plan_backfill(
    profile: SourceProfile,
    *,
    current_year: Optional[int] = None,
    records_provider: FtpRecordsProvider = default_ftp_records,
    api_backfill_years: int = _API_BACKFILL_YEARS,
) -> List[FetchUnit]:
    """Full-history units for ``profile`` ("sair tudo")."""
    if not profile.auto:
        return []
    year_now = current_year or _now_year()

    if profile.kind.is_ftp():
        floor = profile.min_year or year_now
        years = range(floor, year_now + 1)
        return _ftp_units(profile, list(years), records_provider)

    if profile.kind is Kind.API_WINDOW:
        floor = profile.min_year or (year_now - api_backfill_years + 1)
        return _api_window_units(profile.source, range(floor, year_now + 1))

    if profile.kind is Kind.CRAWLER:
        return [FetchUnit(source=profile.source, kind=Kind.CRAWLER)]

    return []


def plan_update(
    profile: SourceProfile,
    ledger: Ledger,
    *,
    current_year: Optional[int] = None,
    records_provider: FtpRecordsProvider = default_ftp_records,
    update_lookback_years: int = 1,
) -> List[FetchUnit]:
    """Delta units: what the ledger doesn't already have, unchanged, at source.

    The recent-window discovery (default: current year and the previous one)
    catches both brand-new monthly files and grown current-year annual files
    (via the ``src_size`` volumetria check in ``Ledger.satisfied``).
    """
    if not profile.auto:
        return []
    year_now = current_year or _now_year()
    index = ledger.index()

    if profile.kind.is_ftp():
        low = max(profile.min_year or year_now, year_now - update_lookback_years)
        units = _ftp_units(profile, list(range(low, year_now + 1)), records_provider)
        return [u for u in units if not ledger.satisfied(u, index=index)]

    if profile.kind is Kind.API_WINDOW:
        last = ledger.max_year(profile.source)
        # Re-pull the last known year (it may have grown) plus any newer years.
        low = last if last is not None else year_now
        return _api_window_units(profile.source, range(low, year_now + 1))

    if profile.kind is Kind.CRAWLER:
        return [FetchUnit(source=profile.source, kind=Kind.CRAWLER)]

    return []
