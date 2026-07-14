"""Bronze tree layout: where each :class:`FetchUnit` lands on disk.

The tree is the browsable artefact the FTP/web front-end sits on top of. It is
built purely from a unit's native coordinates, in a fixed order::

    <SOURCE>/<group>/<state>/<year>/<month>/<file>.csv

Coordinates that don't apply to a source are simply absent, so an annual
national source is shallow (``SINAN/DENG/2024/DENGBR24.csv``) and a monthly
per-state source is deep (``SIH/RD/PR/2024/01/RDPR2401.csv``). The CSV keeps the
official file's own basename, so bronze stays 1:1 traceable to the DATASUS file.
"""
from __future__ import annotations

from pathlib import Path

from guaraci.orchestrator.model import FetchUnit, Kind


def _sanitize(part: str) -> str:
    """Keep path segments filesystem-safe and predictable."""
    return "".join(c for c in part if c.isalnum() or c in ("-", "_", ".")).strip() or "_"


def relative_dir(unit: FetchUnit, tier: str = "raw") -> Path:
    """Relative bronze directory for ``unit`` (below the bronze root).

    ``tier`` namespaces the two offerings: ``raw`` (the official file as-is) and
    ``refined`` (the month-partitioned browsable view). See ``refine.py`` for the
    refined leaf paths, which carry a derived month.
    """
    segments = [tier, unit.source.upper()]
    if unit.group:
        segments.append(_sanitize(unit.group.upper()))
    if unit.state:
        segments.append(_sanitize(unit.state.upper()))
    if unit.year is not None:
        segments.append(f"{unit.year:04d}")
    elif unit.start_date:
        segments.append(_sanitize(unit.start_date[:4]))  # window year
    if unit.month is not None:
        segments.append(f"{unit.month:02d}")
    return Path(*segments)


def filename(unit: FetchUnit) -> str:
    """Canonical CSV filename for ``unit``.

    FTP units keep the official DATASUS basename (e.g. ``DENGBR24`` ->
    ``DENGBR24.csv``) so bronze is auditable against the source. Non-FTP units
    get a coordinate-derived name.
    """
    if unit.src_basename:
        stem = Path(unit.src_basename).stem
        return f"{_sanitize(stem)}.csv"
    bits = [unit.source]
    for value in (unit.group, unit.state):
        if value:
            bits.append(_sanitize(value))
    if unit.year is not None:
        bits.append(f"{unit.year:04d}" + (f"{unit.month:02d}" if unit.month else ""))
    elif unit.start_date:
        bits.append(f"{unit.start_date}_{unit.end_date}")
    return "_".join(bits) + ".csv"


def bronze_path(root: Path, unit: FetchUnit, tier: str = "raw") -> Path:
    """Absolute path of the bronze CSV for ``unit`` under ``root``."""
    return Path(root) / relative_dir(unit, tier) / filename(unit)


def crawler_dir(root: Path, unit: FetchUnit, tier: str = "raw") -> Path:
    """Output directory for a whole-portal crawler source (SNIS/SINISA).

    Crawlers materialise a folder tree (raw/extracted/manifest), not a single
    CSV, so they land under their own source directory (raw tier only).
    """
    if unit.kind is not Kind.CRAWLER:  # defensive; callers pass crawler units
        return bronze_path(root, unit, tier).parent
    return Path(root) / tier / unit.source.upper()
