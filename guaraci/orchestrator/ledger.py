"""The append-only CSV ledger — the heart of incremental extraction.

Every materialised (or attempted) partition writes one row. The ledger is:

* the **state** the updater reads to know the last thing saved per partition and
  fetch only the next / changed one ("bater volumetria": a row records the source
  file's ``src_size`` so a grown current-year file is re-pulled, not skipped);
* the **public manifest** of what exists, that the FTP/web front-end can read.

It is strictly append-only: a re-run of a partition appends a fresh row, and
readers keep the latest row per ``partition_key``. That keeps the file a durable
audit log rather than mutable state.
"""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

from guaraci.orchestrator.model import FetchUnit

# Terminal statuses recorded per unit.
STATUS_OK = "ok"            # bronze CSV materialised
STATUS_EMPTY = "empty"      # source/run produced no rows (re-checked next run)
STATUS_ERROR = "error"      # download/decode/export failed
STATUS_SKIPPED = "skipped"  # already satisfied (idempotent no-op)
STATUS_PLANNED = "planned"  # dry-run: would fetch, nothing written

FIELDS: List[str] = [
    "run_id",
    "ts_utc",
    "source",
    "kind",
    "granularity",
    "group",
    "state",
    "year",
    "month",
    "window_start",
    "window_end",
    "status",
    "documents_found",
    "downloaded_count",
    "refined_count",
    "n_bytes",
    "src_basename",
    "src_size",
    "out_path",
    "error",
    "partition_key",
]


def _opt_int(value: object) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


@dataclass
class LedgerRow:
    """One row of the ledger — a single partition attempt."""

    run_id: str
    ts_utc: str
    source: str
    kind: str
    granularity: str
    status: str
    partition_key: str
    group: str = ""
    state: str = ""
    year: Optional[int] = None
    month: Optional[int] = None
    window_start: str = ""
    window_end: str = ""
    documents_found: int = 0
    downloaded_count: int = 0
    refined_count: int = 0
    n_bytes: int = 0
    src_basename: str = ""
    src_size: int = 0
    out_path: str = ""
    error: str = ""

    def to_csv_dict(self) -> Dict[str, object]:
        row = asdict(self)
        # Normalise None -> "" so the CSV stays clean/round-trippable.
        return {key: ("" if row.get(key) is None else row[key]) for key in FIELDS}

    @classmethod
    def from_csv_dict(cls, row: Dict[str, str]) -> "LedgerRow":
        return cls(
            run_id=row.get("run_id", ""),
            ts_utc=row.get("ts_utc", ""),
            source=row.get("source", ""),
            kind=row.get("kind", ""),
            granularity=row.get("granularity", ""),
            status=row.get("status", ""),
            partition_key=row.get("partition_key", ""),
            group=row.get("group", ""),
            state=row.get("state", ""),
            year=_opt_int(row.get("year")),
            month=_opt_int(row.get("month")),
            window_start=row.get("window_start", ""),
            window_end=row.get("window_end", ""),
            documents_found=_opt_int(row.get("documents_found")) or 0,
            downloaded_count=_opt_int(row.get("downloaded_count")) or 0,
            refined_count=_opt_int(row.get("refined_count")) or 0,
            n_bytes=_opt_int(row.get("n_bytes")) or 0,
            src_basename=row.get("src_basename", ""),
            src_size=_opt_int(row.get("src_size")) or 0,
            out_path=row.get("out_path", ""),
            error=row.get("error", ""),
        )


class Ledger:
    """Append-only CSV ledger at ``path``."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    # -- writing --------------------------------------------------------------

    def append(self, row: LedgerRow) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        new_file = not self.path.exists() or self.path.stat().st_size == 0
        with self.path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDS)
            if new_file:
                writer.writeheader()
            writer.writerow(row.to_csv_dict())

    # -- reading --------------------------------------------------------------

    def read_all(self) -> List[LedgerRow]:
        if not self.path.exists():
            return []
        with self.path.open("r", newline="", encoding="utf-8") as fh:
            return [LedgerRow.from_csv_dict(row) for row in csv.DictReader(fh)]

    def index(self) -> Dict[str, LedgerRow]:
        """Latest row per ``partition_key`` (later appends win)."""
        latest: Dict[str, LedgerRow] = {}
        for row in self.read_all():
            latest[row.partition_key] = row
        return latest

    def satisfied(self, unit: FetchUnit, *, index: Optional[Dict[str, LedgerRow]] = None) -> bool:
        """True if ``unit`` is already materialised and unchanged at the source.

        A prior ``ok`` row satisfies the unit only when the source file size is
        unchanged (or unknown). A grown current-year file (larger ``src_size``)
        is therefore *not* satisfied and will be re-pulled — this is the
        volumetria check that keeps SINAN/SIM current-year data fresh.
        """
        idx = self.index() if index is None else index
        row = idx.get(unit.partition_key())
        if row is None or row.status != STATUS_OK:
            return False
        if unit.src_size and row.src_size and unit.src_size != row.src_size:
            return False
        return True

    def max_year(self, source: str) -> Optional[int]:
        """Highest year with an ``ok``/``empty`` row for ``source`` (API-window)."""
        years = [
            row.year
            for row in self.read_all()
            if row.source == source
            and row.year is not None
            and row.status in (STATUS_OK, STATUS_EMPTY)
        ]
        return max(years) if years else None
