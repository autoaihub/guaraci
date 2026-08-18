"""Pure parsing helpers for INMET historical automatic-station CSV files.

INMET (https://portal.inmet.gov.br) publishes one ZIP per year under
``https://portal.inmet.gov.br/uploads/dadoshistoricos/<AAAA>.zip`` holding one
CSV per automatic weather station. Verified live on 2026-08-17/18 against the
real 2000.zip and 2025.zip archives:

- Encoding is ``latin-1``; field separator is ``;``; decimal separator is
  ``,`` (Brazilian convention).
- Every station CSV starts with EXACTLY 8 metadata lines (region, UF, station
  name, WMO code, latitude, longitude, altitude, foundation date) followed by
  one tabular header line, then hourly data rows. Confirmed across both the
  oldest (2000, 5 stations) and a recent full year (2025, 594 stations).
- The tabular header/rows end with a trailing ``;`` (one spurious empty
  trailing field) in every observed file.
- Missing values are encoded as an empty string in recent years and as the
  sentinel ``-9999`` in the earliest (2000-era) files; both are treated as
  null.
- The exact metadata label text and date/hour column formats drift slightly
  across the 2000-2026 range (e.g. ``Data`` vs ``DATA (YYYY-MM-DD)``,
  ``2025/01/01`` vs ``2000-05-07``, ``0000 UTC`` vs ``00:00``). This module
  normalizes those variants instead of hardcoding one year's exact strings.

Nothing here performs I/O; the datasource wires this to the HTTP client and
zip extraction.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

META_LINE_COUNT = 8
MISSING_SENTINELS = frozenset({"", "-9999", "-9999.0", "-9999,0"})

# Basename pattern: INMET_<REGIAO>_<UF>_<CODIGO>_<ESTACAO>_<INICIO>_A_<FIM>.CSV
STATION_FILENAME_RE = re.compile(
    r"^INMET_(?P<region>[A-Za-z]+)_(?P<uf>[A-Za-z]{2})_(?P<code>[A-Za-z0-9]+)_"
    r"(?P<name>.+)_(?P<start>\d{2}-\d{2}-\d{4})_A_(?P<end>\d{2}-\d{2}-\d{4})\.csv$",
    re.IGNORECASE,
)

BASE_COLUMNS: Tuple[str, ...] = (
    "year",
    "uf",
    "region",
    "station_name",
    "station_code",
    "latitude",
    "longitude",
    "altitude",
    "founded_date",
    "date",
    "hour_utc",
    "timestamp",
)


class InmetParseError(ValueError):
    """Raised when a station CSV does not match the expected shape."""


@dataclass(frozen=True)
class StationFileInfo:
    """Metadata parsed from a station CSV's filename (zip member basename)."""

    region: str
    uf: str
    code: str
    name: str


def slugify(text: str) -> str:
    """ASCII-safe, lowercase, underscore-separated slug for a column label."""
    normalized = unicodedata.normalize("NFD", text)
    without_accents = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    lowered = without_accents.lower()
    slug = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
    return slug or "col"


def parse_station_filename(filename: str) -> Optional[StationFileInfo]:
    """Extract region/UF/code/name from a station CSV basename.

    Returns ``None`` when the name does not match the documented pattern
    (member is skipped by the datasource rather than raising).
    """
    match = STATION_FILENAME_RE.match(filename)
    if not match:
        return None
    return StationFileInfo(
        region=match.group("region").upper(),
        uf=match.group("uf").upper(),
        code=match.group("code").upper(),
        name=match.group("name").strip(),
    )


def parse_decimal(raw: str) -> Optional[float]:
    """Parse a Brazilian-style decimal (comma separator); ``None`` if missing."""
    cleaned = raw.strip()
    if cleaned in MISSING_SENTINELS:
        return None
    try:
        return float(cleaned.replace(".", "").replace(",", ".")) if "," in cleaned else float(cleaned)
    except ValueError:
        return None


def parse_date_token(raw: str) -> Optional[str]:
    """Normalize a date cell (``YYYY/MM/DD`` or ``YYYY-MM-DD``) to ISO 8601."""
    cleaned = raw.strip()
    if not cleaned:
        return None
    normalized = cleaned.replace("/", "-")
    parts = normalized.split("-")
    if len(parts) != 3:
        return None
    year, month, day = parts
    if len(year) != 4 or not (year.isdigit() and month.isdigit() and day.isdigit()):
        return None
    return f"{year}-{int(month):02d}-{int(day):02d}"


def parse_hour_token(raw: str) -> Optional[str]:
    """Normalize an hour cell (``0000 UTC`` or ``00:00``) to ``HH:MM``."""
    cleaned = raw.strip().upper().replace("UTC", "").strip()
    if not cleaned:
        return None
    if ":" in cleaned:
        hh, _, mm = cleaned.partition(":")
    elif len(cleaned) == 4 and cleaned.isdigit():
        hh, mm = cleaned[:2], cleaned[2:]
    else:
        return None
    if not (hh.isdigit() and mm.isdigit()):
        return None
    return f"{int(hh):02d}:{int(mm):02d}"


def _split_row(line: str) -> List[str]:
    stripped = line.rstrip("\r")
    if stripped.endswith(";"):
        stripped = stripped[:-1]
    return stripped.split(";")


def parse_station_csv(
    raw_bytes: bytes,
    *,
    year: int,
    file_info: StationFileInfo,
) -> Tuple[Dict[str, object], List[Dict[str, object]], List[str]]:
    """Parse one station CSV (already-read zip member bytes) into tidy rows.

    Returns ``(metadata, records, warnings)``. ``metadata`` mirrors the 8
    header lines (as parsed, not necessarily identical to the filename).
    ``records`` is a list of dicts, one per hourly observation, with
    :data:`BASE_COLUMNS` plus one slugified column per measured variable.
    """
    warnings: List[str] = []
    text = raw_bytes.decode("latin-1")
    lines = text.split("\n")
    if len(lines) <= META_LINE_COUNT + 1:
        raise InmetParseError(
            f"Station CSV for {file_info.code} ({year}) has only {len(lines)} "
            "lines; expected metadata + header + data rows."
        )

    metadata = _parse_metadata_block(lines[:META_LINE_COUNT])
    header_cells = _split_row(lines[META_LINE_COUNT])
    if len(header_cells) < 3:
        raise InmetParseError(
            f"Station CSV for {file_info.code} ({year}) has an unexpected "
            f"tabular header: {header_cells!r}"
        )
    variable_labels = header_cells[2:]
    variable_slugs = [slugify(label) for label in variable_labels]

    latitude = parse_decimal(str(metadata.get("latitude", "")))
    longitude = parse_decimal(str(metadata.get("longitude", "")))
    altitude = parse_decimal(str(metadata.get("altitude", "")))

    records: List[Dict[str, object]] = []
    for line_no, line in enumerate(lines[META_LINE_COUNT + 1 :], start=META_LINE_COUNT + 2):
        if not line.strip():
            continue
        cells = _split_row(line)
        if len(cells) < 2:
            warnings.append(
                f"{file_info.code} ({year}) line {line_no}: skipped malformed row."
            )
            continue
        date_iso = parse_date_token(cells[0])
        hour_norm = parse_hour_token(cells[1])
        values = cells[2:]
        row: Dict[str, object] = {
            "year": year,
            "uf": file_info.uf,
            "region": metadata.get("region") or file_info.region,
            "station_name": metadata.get("station_name") or file_info.name,
            "station_code": metadata.get("station_code") or file_info.code,
            "latitude": latitude,
            "longitude": longitude,
            "altitude": altitude,
            "founded_date": metadata.get("founded_date"),
            "date": date_iso,
            "hour_utc": hour_norm,
            "timestamp": f"{date_iso}T{hour_norm}:00" if date_iso and hour_norm else None,
        }
        for slug, raw_value in zip(variable_slugs, values):
            row[slug] = parse_decimal(raw_value)
        records.append(row)

    return metadata, records, warnings


def _parse_metadata_block(meta_lines: Sequence[str]) -> Dict[str, object]:
    metadata: Dict[str, object] = {}
    for line in meta_lines:
        cells = _split_row(line)
        if len(cells) < 2:
            continue
        key = slugify(cells[0])
        value = cells[1].strip()
        if "regiao" in key:
            metadata["region"] = value
        elif key == "uf":
            metadata["uf"] = value
        elif "estacao" in key or "estacao" in key:
            metadata["station_name"] = value
        elif "codigo" in key:
            metadata["station_code"] = value
        elif "latitude" in key:
            metadata["latitude"] = value
        elif "longitude" in key:
            metadata["longitude"] = value
        elif "altitude" in key:
            metadata["altitude"] = value
        elif "fundacao" in key or "fundac" in key:
            metadata["founded_date"] = value
    return metadata
