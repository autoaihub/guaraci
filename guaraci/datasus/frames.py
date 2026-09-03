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


# Lote de escrita no sqlite. Cada lote vira uma cópia pandas antes de ir para
# o banco, então o tamanho é o que define o teto de memória da exportação.
# 50 mil linhas mantêm o pico próximo do parquet sem custo relevante de tempo.
_SQLITE_BATCH_ROWS = 50_000


def write_sqlite(
    frame: Frame,
    *,
    db_path: Path,
    table: str,
    batch_rows: int = _SQLITE_BATCH_ROWS,
) -> Optional[Path]:
    """Grava o frame numa tabela sqlite em lotes de tamanho fixo.

    ``to_pandas()`` sobre o conjunto inteiro era o caminho anterior, e o custo
    não é o do parquet equivalente: as colunas de texto viram objetos Python na
    conversão. Medido sobre 4 milhões de linhas e 10 colunas, o pico era de
    2534 MB acima da linha de base, contra 179 MB do parquet, e crescia
    proporcionalmente ao número de linhas e de colunas.

    Devolve ``None`` quando não há linha alguma, preservando o contrato de
    ``write_frame`` de não deixar arquivo vazio para trás.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tamanho_lote = max(1, int(batch_rows))

    con = sqlite3.connect(db_path)
    escreveu = False
    try:
        for lote in _iter_batches(frame, tamanho_lote):
            if lote.is_empty():
                continue
            lote.to_pandas().to_sql(
                name=table,
                con=con,
                if_exists="append" if escreveu else "replace",
                index=False,
            )
            escreveu = True
    finally:
        con.close()

    if not escreveu:
        # Sem linhas, sqlite3.connect já criou um arquivo vazio; deixá-lo em
        # disco faria uma coleta sem resultado parecer bem-sucedida.
        db_path.unlink(missing_ok=True)
        return None
    return db_path


def _iter_batches(frame: Frame, batch_rows: int):
    """Percorre o frame em pedaços, sem materializar o conjunto inteiro."""
    if isinstance(frame, pl.LazyFrame):
        offset = 0
        while True:
            lote = frame.slice(offset, batch_rows).collect()
            if lote.is_empty():
                return
            yield lote
            if lote.height < batch_rows:
                return
            offset += batch_rows
        return
    yield from frame.iter_slices(batch_rows)


def write_frame(
    frame: Frame,
    *,
    output_dir: Path,
    stem: str,
    format: str,
) -> Optional[Path]:
    """Escreve o frame no formato pedido, em streaming nos três formatos."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    is_lazy = isinstance(frame, pl.LazyFrame)
    final_path = output_dir / f"{stem}.{format}"

    if format == "csv":
        frame.sink_csv(final_path) if is_lazy else frame.write_csv(final_path)
    elif format == "parquet":
        frame.sink_parquet(final_path) if is_lazy else frame.write_parquet(final_path)
    elif format == "sqlite":
        # O arquivo criado é `.db`, e é ele que precisa ser devolvido: retornar
        # `final_path` fazia o manifesto e o "wrote 1 file" da CLI apontarem
        # para um `.sqlite` que nunca existiu.
        return write_sqlite(frame, db_path=output_dir / f"{stem}.db", table=stem)
    else:
        raise ValueError("Formato inválido. Escolha entre 'csv', 'sqlite' ou 'parquet'.")

    return final_path
