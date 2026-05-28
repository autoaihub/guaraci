"""DATASUS file-name parsing.

Single source of truth for translating a basename on
``ftp.datasus.gov.br`` into structured identity (system, group, UF, year,
optional month). Today this logic is implicit in PySUS and partially
duplicated inside :mod:`guaraci.datasus.sih`; centralising it here lets
the FTP layer stay source-agnostic.

The known patterns are:

- SIH:   ``<GROUP><UF><YY><MM>.dbc``   (e.g. ``RDSP2401.dbc``)
- SIM:   ``DO<UF><YYYY>.dbc``  (CID-10, 1996+)
         ``MORT<UF><YYYY>.dbc`` (CID-9, 1979–1995)
- SINAN: ``<DISEASE>BR<YY>.dbc`` (consolidated yearly file)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import Enum
from typing import Optional


class System(str, Enum):
    SIH = "SIH"
    SIM = "SIM"
    SINAN = "SINAN"


@dataclass(frozen=True)
class FileRecord:
    """Identity of a DATASUS file on the FTP server.

    Immutable, JSON-serializable, hashable. ``path`` is the absolute
    server path (directory + basename) when known; the catalog parsers
    leave it blank and the discovery layer fills it in.
    """

    basename: str
    system: System
    group: str
    state: Optional[str]
    year: int
    month: Optional[int] = None
    size: int = 0
    path: str = ""

    def to_dict(self) -> dict:
        return {
            "basename": self.basename,
            "system": self.system.value,
            "group": self.group,
            "state": self.state,
            "year": self.year,
            "month": self.month,
            "size": self.size,
            "path": self.path,
        }

    def with_path(self, full_path: str) -> "FileRecord":
        return replace(self, path=full_path)

    def with_size(self, size: int) -> "FileRecord":
        return replace(self, size=int(size))


# --- SIH ---------------------------------------------------------------------

SIH_GROUPS: tuple[str, ...] = ("RD", "RJ", "SP", "ER", "CH", "CM")

_SIH_RE = re.compile(
    r"^(?P<group>RD|RJ|SP|ER|CH|CM)"
    r"(?P<state>[A-Z]{2})"
    r"(?P<yy>\d{2})"
    r"(?P<mm>\d{2})"
    r"\.dbc$",
    re.IGNORECASE,
)


def _yy_to_year(yy: int) -> int:
    """Resolve a 2-digit DATASUS year (SIH/SINAN window starts 1992)."""
    return 1900 + yy if yy >= 92 else 2000 + yy


def parse_sih(basename: str) -> Optional[FileRecord]:
    m = _SIH_RE.match(basename)
    if not m:
        return None
    return FileRecord(
        basename=basename,
        system=System.SIH,
        group=m.group("group").upper(),
        state=m.group("state").upper(),
        year=_yy_to_year(int(m.group("yy"))),
        month=int(m.group("mm")),
    )


# --- SIM ---------------------------------------------------------------------

_SIM_CID10_RE = re.compile(
    r"^DO(?P<state>[A-Z]{2})(?P<year>\d{4})\.dbc$",
    re.IGNORECASE,
)
_SIM_CID9_RE = re.compile(
    r"^MORT(?P<state>[A-Z]{2})(?P<year>\d{4})\.dbc$",
    re.IGNORECASE,
)


def parse_sim(basename: str) -> Optional[FileRecord]:
    m = _SIM_CID10_RE.match(basename)
    if m:
        return FileRecord(
            basename=basename,
            system=System.SIM,
            group="CID10",
            state=m.group("state").upper(),
            year=int(m.group("year")),
        )
    m = _SIM_CID9_RE.match(basename)
    if m:
        return FileRecord(
            basename=basename,
            system=System.SIM,
            group="CID9",
            state=m.group("state").upper(),
            year=int(m.group("year")),
        )
    return None


# --- SINAN -------------------------------------------------------------------

_SINAN_NATIONAL_RE = re.compile(
    r"^(?P<group>[A-Z]+)BR(?P<yy>\d{2})\.dbc$",
    re.IGNORECASE,
)


def parse_sinan(basename: str) -> Optional[FileRecord]:
    m = _SINAN_NATIONAL_RE.match(basename)
    if not m:
        return None
    return FileRecord(
        basename=basename,
        system=System.SINAN,
        group=m.group("group").upper(),
        state=None,
        year=_yy_to_year(int(m.group("yy"))),
    )


# --- Dispatcher --------------------------------------------------------------

def parse(basename: str) -> Optional[FileRecord]:
    """Try every known DATASUS pattern. Returns ``None`` if nothing matches."""
    for parser in (parse_sih, parse_sim, parse_sinan):
        record = parser(basename)
        if record is not None:
            return record
    return None
