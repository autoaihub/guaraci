"""DBC decoder façade.

DATASUS distributes data as ``.dbc`` (compressed DBF). ``pyreaddbc`` 2.x
exposes :func:`pyreaddbc.dbc2dbf`, which writes the decompressed ``.dbf``
to disk; from there :mod:`dbfread` yields records. This module wraps both
into the single primitive promised by the plan:

    ``read(path: Path) -> polars.DataFrame``

We use latin-1 by default — the historical encoding of DATASUS files —
and ignore decode errors so 1990s files with stray bytes still load.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Union

import polars as pl

PathLike = Union[str, Path]


def read(path: PathLike, *, encoding: str = "latin-1") -> pl.DataFrame:
    """Decode a DBC file and return a :class:`polars.DataFrame`.

    The pipeline is ``DBC → DBF (temp file) → records → Polars``. The
    intermediate ``.dbf`` is deleted before this function returns.
    """
    try:
        from pyreaddbc import dbc2dbf
    except ImportError as exc:  # pragma: no cover - dep guard
        raise ImportError(
            "pyreaddbc is required for DBC decoding. "
            "Install with: pip install 'guaraci[datasus]'"
        ) from exc

    try:
        from dbfread import DBF
    except ImportError as exc:  # pragma: no cover - dep guard
        raise ImportError(
            "dbfread is required for DBC decoding. "
            "Install with: pip install 'guaraci[datasus]'"
        ) from exc

    src = Path(path)
    if not src.exists():
        raise FileNotFoundError(src)

    with tempfile.TemporaryDirectory(prefix="guaraci_dbc_") as tmp:
        dbf_path = Path(tmp) / (src.stem + ".dbf")
        dbc2dbf(str(src), str(dbf_path))
        records = list(
            DBF(
                str(dbf_path),
                encoding=encoding,
                char_decode_errors="ignore",
                lowernames=False,
            )
        )

    if not records:
        return pl.DataFrame()

    # `pl.DataFrame(list[dict])` infers schema column-by-column. Going
    # through pandas first is more forgiving for legacy DBF columns where
    # individual records may contain mixed types (None + str).
    try:
        return pl.DataFrame(records)
    except Exception:
        import pandas as pd

        return pl.from_pandas(pd.DataFrame.from_records(records))
