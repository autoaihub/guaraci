"""The **refined** bronze tier: the raw file, repartitioned by month.

This is the "bronze mais refinado, porém não prata": it takes a raw official
file and lays its rows out in the browsable ``<source>/<group>/<year>/<month>``
tree the front-end wants — by splitting on the record's event date. It does
*not* rename columns, harmonise schemas, join sources or clean values, so it
stays bronze, not silver. It is a pure repartition of raw.

Safety: the month is derived with the file's own ``year`` as an oracle. For each
value we try the common DATASUS date encodings (ISO, ``YYYYMMDD``, ``DDMMYYYY``,
``YYYYMM``, ``MMYYYY``) and accept the first whose year matches the file's year.
A value we can't place (bad date, or a year different from the file's) goes to an
``unknown`` month bucket (``00``) — never silently mis-bucketed, never dropped.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

from guaraci.orchestrator.model import FetchUnit
from guaraci.orchestrator.paths import _sanitize, filename

# Source -> event-date column to partition by. Extend as needed; a source not
# listed (or whose column is absent from the frame) falls back to year-level.
EVENT_DATE_COLUMN = {
    "sinan": "DT_NOTIFIC",
    "sim": "DTOBITO",
    "sinasc": "DTNASC",
}

UNKNOWN_MONTH = 0  # rows whose date can't be placed in the file's year


def month_in_year(value: object, year: int) -> int:
    """Return the 1..12 month of ``value`` if it falls in ``year``, else 0.

    Format-agnostic: the year acts as an oracle, so we never need to know the
    exact DATASUS encoding up front and never mis-bucket on a wrong guess.
    """
    if value is None:
        return UNKNOWN_MONTH
    text = str(value).strip()
    if not text:
        return UNKNOWN_MONTH
    y = f"{year:04d}"

    # ISO-ish: YYYY-MM-DD / YYYY/MM/DD
    iso = re.match(r"^(\d{4})[-/](\d{2})", text)
    if iso and iso.group(1) == y:
        return _valid_month(iso.group(2))

    digits = re.sub(r"\D", "", text)
    if len(digits) == 8:
        if digits[0:4] == y:            # YYYYMMDD
            return _valid_month(digits[4:6])
        if digits[4:8] == y:            # DDMMYYYY
            return _valid_month(digits[2:4])
    elif len(digits) == 6:
        if digits[0:4] == y:            # YYYYMM
            return _valid_month(digits[4:6])
        if digits[2:6] == y:            # MMYYYY
            return _valid_month(digits[0:2])
    return UNKNOWN_MONTH


def _valid_month(mm: str) -> int:
    try:
        month = int(mm)
    except ValueError:
        return UNKNOWN_MONTH
    return month if 1 <= month <= 12 else UNKNOWN_MONTH


def refined_relative_dir(unit: FetchUnit, month: Optional[int]) -> Path:
    """Relative directory of a refined partition (below the bronze root)."""
    segments = ["refined", unit.source.upper()]
    if unit.group:
        segments.append(_sanitize(unit.group.upper()))
    if unit.state:
        segments.append(_sanitize(unit.state.upper()))
    segments.append(f"{unit.year:04d}" if unit.year is not None else "unknown")
    if month is not None:
        segments.append(f"{month:02d}")
    return Path(*segments)


def _refined_name(unit: FetchUnit, month: Optional[int]) -> str:
    stem = Path(filename(unit)).stem
    if month is None:
        return f"{stem}.csv"
    return f"{stem}-{unit.year:04d}{month:02d}.csv"


def write_refined(frame, unit: FetchUnit, root: Path) -> List[Path]:
    """Write ``frame`` (the raw file's rows) as month partitions under ``root``.

    Returns the list of refined CSV paths written. Monthly units (SIH, etc.)
    already know their month and pass through unchanged; annual units with a
    known event-date column are split by month; anything else lands at
    year-level (a single refined file, no month split).
    """
    import polars as pl

    root = Path(root)
    partitions: List[Tuple[Optional[int], object]] = []

    if unit.month is not None:
        # Already at native monthly granularity — no date parsing needed.
        partitions.append((unit.month, frame))
    else:
        column = EVENT_DATE_COLUMN.get(unit.source)
        if not column or column not in frame.columns or unit.year is None:
            partitions.append((None, frame))  # can't split -> year level
        else:
            months = frame.get_column(column).map_elements(
                lambda v: month_in_year(v, unit.year), return_dtype=pl.Int64
            )
            tagged = frame.with_columns(months.alias("__month__"))
            for key, sub in tagged.group_by(["__month__"], maintain_order=True):
                month_value = key[0] if isinstance(key, (tuple, list)) else key
                partitions.append((int(month_value), sub.drop("__month__")))

    written: List[Path] = []
    for month, sub in partitions:
        target = root / refined_relative_dir(unit, month) / _refined_name(unit, month)
        target.parent.mkdir(parents=True, exist_ok=True)
        sub.write_csv(target)
        written.append(target)
    return written
