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

import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Union

import polars as pl
from loguru import logger

PathLike = Union[str, Path]

# Tamanho do chunk de leitura DBF: grande o bastante para inferência de schema
# estável, pequeno o bastante para não materializar milhões de dicts de uma vez.
# Pico de memória medido sobre DENGBR23.dbc (62 MB comprimidos), com o tempo
# estável em 180-200 s nas quatro configurações: 100k linhas custam 2815 MB;
# 25k custam 1408 MB; 10k custam 960 MB; 5k custam 878 MB. O ganho satura
# perto de 10k, que é onde o valor foi fixado.
_CHUNK_ROWS = 10_000


class DbcDependencyError(ImportError):
    """As dependências de decodificação DBC não estão instaladas.

    Herda de :class:`ImportError` para que o orquestrador reconheça a falha
    como determinística (não adianta tentar o próximo arquivo) e aborte a
    execução antes de baixar centenas de megabytes que seriam descartados.
    """


def ensure_available() -> None:
    """Valida as dependências de decodificação antes de qualquer download.

    ``read`` importa ``pyreaddbc``/``dbfread`` tardiamente, já com o arquivo
    baixado. Numa coleta de vários anos isso significa transferir o conjunto
    inteiro para só então descobrir que nada pode ser decodificado. Esta
    função existe para ser chamada no início da orquestração.
    """
    missing = []
    try:
        import dbfread  # noqa: F401
    except ImportError:
        missing.append("dbfread")
    try:
        import pyreaddbc  # noqa: F401
    except ImportError:
        missing.append("pyreaddbc")

    if missing:
        raise DbcDependencyError(
            f"Decodificação de DBC indisponível: falta {', '.join(missing)}. "
            "Instale com: pip install 'guaraci[datasus]'"
        )


def _frame_from_records_static(records: list) -> pl.DataFrame:
    """Build a DataFrame from a batch of DBF records.

    ``pl.DataFrame(list[dict])`` infers the schema column-by-column. Going
    through pandas first is more forgiving for legacy DBF columns where
    individual records may contain mixed types (``None`` + ``str``).
    """
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
        raise DbcDependencyError(
            "dbfread is required for DBC decoding. "
            "Install with: pip install 'guaraci[datasus]'"
        ) from exc

    src = Path(path)
    if not src.exists():
        raise FileNotFoundError(src)

    _frame_from_records = _frame_from_records_static

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

    with _as_dbf(src) as dbf_path:
        return _frame_from_dbf(dbf_path)


@contextmanager
def _as_dbf(src: Path) -> Iterator[Path]:
    """Yield a readable ``.dbf`` for ``src``, decompressing it if needed.

    ``.dbf`` inputs are used in place; ``.dbc`` inputs are decompressed into
    a temporary directory that is removed on exit.
    """
    if src.suffix.lower() == ".dbf":
        yield src
        return

    try:
        from pyreaddbc import dbc2dbf
    except ImportError as exc:  # pragma: no cover - dep guard
        raise DbcDependencyError(
            "pyreaddbc is required for DBC decoding. "
            "Install with: pip install 'guaraci[datasus]'"
        ) from exc

    with tempfile.TemporaryDirectory(prefix="guaraci_dbc_") as tmp:
        dbf_path = Path(tmp) / (src.stem + ".dbf")
        dbc2dbf(str(src), str(dbf_path))
        yield dbf_path


def decode_to_parquet(
    src: PathLike,
    dest: PathLike,
    *,
    encoding: str = "latin-1",
) -> Path:
    """Decode a DBC/DBF straight to parquet without holding the table in RAM.

    :func:`read` materialises every chunk as a DataFrame and concatenates
    them, so peak memory scales with the whole file: a single year of SINAN
    dengue (287 MB compressed) was measured at 8.8 GB resident. Here each
    chunk is flushed to its own parquet part and the parts are streamed into
    ``dest``, so the peak scales with :data:`_CHUNK_ROWS` instead.

    Falls back to the in-memory path when the parts turn out to have
    incompatible schemas, which ``vertical_relaxed`` can reconcile and the
    parquet scan cannot.
    """
    try:
        from dbfread import DBF
    except ImportError as exc:  # pragma: no cover - dep guard
        raise DbcDependencyError(
            "dbfread is required for DBC decoding. "
            "Install with: pip install 'guaraci[datasus]'"
        ) from exc

    src_path = Path(src)
    if not src_path.exists():
        raise FileNotFoundError(src_path)
    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    with _as_dbf(src_path) as dbf_path, tempfile.TemporaryDirectory(
        prefix="guaraci_parts_"
    ) as tmp:
        parts_dir = Path(tmp)
        parts: list[Path] = []

        def _flush(chunk: list) -> None:
            part = parts_dir / f"part_{len(parts):05d}.parquet"
            _frame_from_records_static(chunk).write_parquet(part)
            parts.append(part)

        table = DBF(
            str(dbf_path),
            encoding=encoding,
            char_decode_errors="ignore",
            lowernames=False,
        )
        chunk: list = []
        for record in table:
            chunk.append(record)
            if len(chunk) >= _CHUNK_ROWS:
                _flush(chunk)
                chunk = []
        if chunk:
            _flush(chunk)

        if not parts:
            pl.DataFrame().write_parquet(dest_path)
            return dest_path
        if len(parts) == 1:
            # Um único chunk: nada a unir, basta promover o part ao destino.
            shutil.move(str(parts[0]), str(dest_path))
            return dest_path

        try:
            # Um `scan_parquet` sobre a lista exigiria schema idêntico em
            # todas as partes, o que não acontece: uma coluna vazia num chunk
            # é inferida como Null e como Date no seguinte. O concat lazy
            # resolve o supertipo entre elas sem sair do streaming; sem isso
            # a junção caía no fallback em memória e o pico voltava a
            # acompanhar o arquivo inteiro.
            pl.concat(
                [pl.scan_parquet(part) for part in parts], how="diagonal_relaxed"
            ).sink_parquet(dest_path)
        except Exception as exc:
            logger.warning(
                "Streaming merge failed for {} ({}); falling back to in-memory concat",
                dest_path.name,
                exc,
            )
            frames = [pl.read_parquet(part) for part in parts]
            pl.concat(frames, how="vertical_relaxed").write_parquet(dest_path)
        return dest_path
