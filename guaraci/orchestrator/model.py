"""Core value objects for the bronze orchestrator.

The orchestrator sweeps every registered Guaraci source and materialises the
*raw official file* at its **native granularity** into a browsable bronze tree,
recording one ledger row per partition. No month bifurcation happens here — an
annual source stays annual (SINAN, SIM); a monthly source stays monthly (SIH).
The month-level recorte and the pretty ``disease/year/month`` view belong to a
downstream (silver) processing layer, not to this extractor.

Nothing in this module does I/O; everything here is a pure, hashable value
object so the planner and the tests can reason about units without a network.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Kind(str, Enum):
    """How a source is shaped, which decides discovery + run + path strategy."""

    FTP_SINAN = "ftp_sinan"          # per disease, annual, national (no state)
    FTP_SIM = "ftp_sim"              # per group(CID)/UF, annual
    FTP_SIH = "ftp_sih"              # per group/UF, monthly (competência)
    FTP_GENERIC = "ftp_generic"      # spec-driven (SINASC, SIA, CNES, PNI, ...)
    API_WINDOW = "api_window"        # OpenDataSUS: date-window / year, no disease
    API_POINT = "api_point"          # NASA: needs lat/lon — not auto-backfillable
    CRAWLER = "crawler"              # gov.br (SNIS/SINISA): whole-portal crawl
    UNKNOWN = "unknown"

    def is_ftp(self) -> bool:
        return self in (
            Kind.FTP_SINAN,
            Kind.FTP_SIM,
            Kind.FTP_SIH,
            Kind.FTP_GENERIC,
        )


class Granularity(str, Enum):
    """Native granularity of a single materialised bronze file."""

    MONTHLY = "monthly"
    ANNUAL = "annual"
    WINDOW = "window"
    IRREGULAR = "irregular"


class Cadence(str, Enum):
    """How often the source publishes new data — drives the update check rhythm.

    This is the "config de cadência por fonte": the updater re-checks a source
    on this rhythm and pulls whatever is newly available, instead of a single
    fixed monthly sweep for everything.
    """

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    ANNUAL = "annual"
    IRREGULAR = "irregular"

    def period_days(self) -> Optional[int]:
        """Approximate re-check period in days (None for irregular/manual)."""
        return {
            Cadence.DAILY: 1,
            Cadence.WEEKLY: 7,
            Cadence.MONTHLY: 30,
            Cadence.ANNUAL: 365,
        }.get(self)


@dataclass(frozen=True)
class FetchUnit:
    """One atomic thing to materialise: exactly one native official file/window.

    For FTP sources a unit maps 1:1 to a DATASUS file (one ``FileRecord``):
    ``group`` carries the disease code for SINAN or the group code otherwise.
    For API-window sources a unit is one ``(uf?, year)`` slice. The coordinates
    that are ``None`` simply don't apply to that source shape.
    """

    source: str
    kind: Kind
    group: Optional[str] = None       # SINAN disease, or group/CID code
    state: Optional[str] = None       # UF, when the source is per-state
    year: Optional[int] = None
    month: Optional[int] = None       # only when the source file is monthly
    start_date: Optional[str] = None  # API-window sources (ISO yyyy-mm-dd)
    end_date: Optional[str] = None
    # Volumetria hints captured at discovery (FTP: the official file identity).
    src_basename: str = ""
    src_path: str = ""
    src_size: int = 0

    @property
    def granularity(self) -> Granularity:
        if self.month is not None:
            return Granularity.MONTHLY
        if self.start_date is not None:
            return Granularity.WINDOW
        if self.year is not None:
            return Granularity.ANNUAL
        return Granularity.IRREGULAR

    def partition_key(self) -> str:
        """Stable identity of this partition, independent of ``src_size``.

        Two units with the same key address the same bronze slot; the ledger
        keeps the latest row per key so a re-run supersedes an older one.
        """
        parts = [
            self.source,
            self.group or "",
            self.state or "",
            "" if self.year is None else str(self.year),
            "" if self.month is None else f"{self.month:02d}",
            self.start_date or "",
            self.end_date or "",
        ]
        return "|".join(parts)

    def label(self) -> str:
        """Short human-readable description for logs/CLI."""
        bits = [self.source]
        if self.group:
            bits.append(self.group)
        if self.state:
            bits.append(self.state)
        if self.year is not None:
            ym = f"{self.year}" + (f"-{self.month:02d}" if self.month else "")
            bits.append(ym)
        elif self.start_date:
            bits.append(f"{self.start_date}..{self.end_date}")
        return "/".join(bits)
