"""Carga e escrita compartilhadas dos microdados já convertidos em parquet.

SIH, SIM e SINAN mantinham cada um a sua cópia de ``_load_as_polars`` e de
``export``, com o mesmo desenho: ler todos os arquivos anuais para memória e
concatená-los com ``how="diagonal"``. Numa coleta de dengue de 2014 a 2024 isso
significa exigir 17 milhões de registros e 121 colunas residentes de uma só vez,
mais a cópia do concat.

Aqui a leitura devolve um plano lazy e a escrita usa ``sink_*`` quando o plano
ainda não foi materializado, de modo que o pico de memória acompanha o bloco em
trânsito e não o conjunto inteiro.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional, Sequence, Union

import polars as pl
from loguru import logger

from guaraci.datasus import filtering

Frame = Union[pl.DataFrame, pl.LazyFrame]


def scan_parquet_group(paths: Sequence[str], *, label: str) -> pl.LazyFrame:
    """Plano lazy sobre os parquets de um grupo, com as UFs normalizadas.

    Os arquivos anuais não compartilham o mesmo conjunto de colunas, e a
    divergência é nos dois sentidos, então cada arquivo entra como seu próprio
    plano e ``diagonal_relaxed`` faz a união. É a semântica do antigo
    ``concat(how="diagonal")``, sem sair do lazy.
    """
    files = [str(path) for path in paths]
    if not files:
        logger.warning(f"No data found for {label}")
        return pl.LazyFrame()

    logger.info(f"Planning {len(files)} parquet files for {label}")
    try:
        plans = [pl.scan_parquet(path) for path in files]
        lf = plans[0] if len(plans) == 1 else pl.concat(plans, how="diagonal_relaxed")
    except Exception as exc:  # noqa: BLE001 - queda para o caminho materializado
        logger.warning(
            f"Lazy scan unavailable for {label} ({exc}); falling back to eager concat"
        )
        return eager_concat_group(files, label=label).lazy()

    uf_columns = filtering.uf_column_names(lf.collect_schema().names())
    if uf_columns:
        lf = lf.with_columns(
            [filtering.uf_normalization_expr(lf, col) for col in uf_columns]
        )
    return lf


def eager_concat_group(paths: Sequence[str], *, label: str) -> pl.DataFrame:
    """Caminho de reserva, materializado, para quando o scan lazy não serve."""
    from tqdm import tqdm

    frames: list[pl.DataFrame] = []
    with tqdm(total=len(paths), desc=f"Loading {label}", unit="file") as pbar:
        for filepath in paths:
            try:
                df = pl.read_parquet(filepath)
                uf_columns = filtering.uf_column_names(df.columns)
                if uf_columns:
                    df = df.with_columns(
                        [filtering.uf_normalization_expr(df, col) for col in uf_columns]
                    )
                frames.append(df)
            except Exception as exc:  # noqa: BLE001 - falha de um arquivo não aborta
                logger.error(f"Failed to process parquet file {filepath}: {exc}")
            finally:
                pbar.update(1)

    if not frames:
        logger.warning(f"No valid data found for {label}")
        return pl.DataFrame()
    return pl.concat(frames, how="diagonal")


def is_empty(frame: Frame) -> bool:
    """Diz se o frame não tem linha alguma, sem materializá-lo por inteiro."""
    if isinstance(frame, pl.LazyFrame):
        return frame.select(pl.len()).collect().item() == 0
    return len(frame) == 0


def row_count(frame: Frame) -> int:
    """Número de linhas do frame, com projeção mínima quando é lazy."""
    if isinstance(frame, pl.LazyFrame):
        return int(frame.select(pl.len()).collect().item())
    return len(frame)


def write_frame(
    frame: Frame,
    *,
    output_dir: Path,
    stem: str,
    format: str,
) -> Optional[Path]:
    """Escreve o frame no formato pedido, em streaming quando possível.

    ``sqlite`` continua materializando: a escrita passa por pandas e não tem
    equivalente incremental aqui.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    is_lazy = isinstance(frame, pl.LazyFrame)
    final_path = output_dir / f"{stem}.{format}"

    if format == "csv":
        frame.sink_csv(final_path) if is_lazy else frame.write_csv(final_path)
    elif format == "parquet":
        frame.sink_parquet(final_path) if is_lazy else frame.write_parquet(final_path)
    elif format == "sqlite":
        materialized = frame.collect() if is_lazy else frame
        if len(materialized) == 0:
            return None
        db_path = output_dir / f"{stem}.db"
        con = sqlite3.connect(db_path)
        try:
            materialized.to_pandas().to_sql(
                name=stem, con=con, if_exists="replace", index=False
            )
        finally:
            con.close()
        return final_path
    else:
        raise ValueError("Formato inválido. Escolha entre 'csv', 'sqlite' ou 'parquet'.")

    return final_path
