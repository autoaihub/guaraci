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

# Tamanho do chunk de leitura DBF: grande o bastante para inferência de schema
# estável, pequeno o bastante para não materializar milhões de dicts de uma vez.
_CHUNK_ROWS = 100_000


def read(path: PathLike, *, encoding: str = "latin-1") -> pl.DataFrame:
    """Decode a DBC (or plain DBF) file into a :class:`polars.DataFrame`.

    For ``.dbc`` the pipeline is ``DBC → DBF (temp file) → records →
    Polars`` (the intermediate ``.dbf`` is deleted before returning). For
    ``.dbf`` inputs — some systems such as PNI distribute uncompressed DBF
    directly — the ``pyreaddbc`` decompression step is skipped and the file
    is read in place.
    """
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

    def _frame_from_records(records: list) -> pl.DataFrame:
        # `pl.DataFrame(list[dict])` infers schema column-by-column. Going
        # through pandas first is more forgiving for legacy DBF columns where
        # individual records may contain mixed types (None + str).
        try:
            return pl.DataFrame(records, infer_schema_length=None)
        except Exception as first_exc:
            import pandas as pd

            try:
                return pl.from_pandas(pd.DataFrame.from_records(records))
            except Exception as second_exc:
                # Preserva a causa original do erro de schema em vez de só a
                # falha do fallback pandas.
                raise second_exc from first_exc

    def _frame_from_dbf(dbf_file: PathLike) -> pl.DataFrame:
        # Iteração em chunks: arquivos grandes (SIH RD nacional) não cabem
        # confortavelmente como list[dict] + DataFrame ao mesmo tempo.
        table = DBF(
            str(dbf_file),
            encoding=encoding,
            char_decode_errors="ignore",
            lowernames=False,
        )
        frames: list[pl.DataFrame] = []
        chunk: list = []
        for record in table:
            chunk.append(record)
            if len(chunk) >= _CHUNK_ROWS:
                frames.append(_frame_from_records(chunk))
                chunk = []
        if chunk:
            frames.append(_frame_from_records(chunk))
        if not frames:
            return pl.DataFrame()
        if len(frames) == 1:
            return frames[0]
        # vertical_relaxed absorve divergências de dtype entre chunks
        # (ex.: coluna toda-nula no primeiro chunk, texto nos seguintes).
        return pl.concat(frames, how="vertical_relaxed")

    if src.suffix.lower() == ".dbf":
        return _frame_from_dbf(src)

    try:
        from pyreaddbc import dbc2dbf
    except ImportError as exc:  # pragma: no cover - dep guard
        raise ImportError(
            "pyreaddbc is required for DBC decoding. "
            "Install with: pip install 'guaraci[datasus]'"
        ) from exc

    with tempfile.TemporaryDirectory(prefix="guaraci_dbc_") as tmp:
        dbf_path = Path(tmp) / (src.stem + ".dbf")
        dbc2dbf(str(src), str(dbf_path))
        return _frame_from_dbf(dbf_path)
