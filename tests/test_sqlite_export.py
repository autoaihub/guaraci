"""Regressão: exportação sqlite grava em lotes e devolve o caminho que existe.

Dois defeitos independentes no mesmo caminho de código:

* ``write_frame`` gravava ``{stem}.db`` e devolvia ``{stem}.sqlite``, de modo
  que o manifesto e o "wrote 1 file" da CLI apontavam para um arquivo que
  nunca existiu.
* A escrita passava por ``to_pandas()`` sobre o conjunto inteiro. Medido sobre
  4 milhões de linhas e 10 colunas, o pico era de 3195 MB acima da linha de
  base, contra 716 MB do parquet equivalente, e crescia com o número de linhas
  e de colunas.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import polars as pl
import pytest

from guaraci.datasus import frames


def _frame(linhas: int) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "NU_NOTIFIC": [str(i) for i in range(linhas)],
            "SG_UF_NOT": ["SP", "RJ"] * (linhas // 2) + ["SP"] * (linhas % 2),
        }
    )


def _linhas_no_banco(db_path: Path, tabela: str) -> int:
    con = sqlite3.connect(db_path)
    try:
        return con.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
    finally:
        con.close()


def test_caminho_devolvido_existe_em_disco(tmp_path: Path) -> None:
    destino = frames.write_frame(
        _frame(10), output_dir=tmp_path, stem="extrato", format="sqlite"
    )

    assert destino is not None
    assert destino.exists(), f"caminho devolvido não existe: {destino}"
    assert destino.name == "extrato.db"


@pytest.mark.parametrize("linhas", [1, 99, 100, 101, 250])
def test_todas_as_linhas_chegam_independente_do_lote(tmp_path: Path, linhas: int) -> None:
    """Os limites do laço de lotes são onde um off-by-one perderia dados."""
    db_path = tmp_path / "extrato.db"
    frames.write_sqlite(_frame(linhas), db_path=db_path, table="extrato", batch_rows=100)

    assert _linhas_no_banco(db_path, "extrato") == linhas


def test_lote_pequeno_e_lote_unico_produzem_o_mesmo_conteudo(tmp_path: Path) -> None:
    origem = _frame(250)
    em_lotes = tmp_path / "lotes.db"
    inteiro = tmp_path / "inteiro.db"

    frames.write_sqlite(origem, db_path=em_lotes, table="t", batch_rows=7)
    frames.write_sqlite(origem, db_path=inteiro, table="t", batch_rows=10**9)

    con_a, con_b = sqlite3.connect(em_lotes), sqlite3.connect(inteiro)
    try:
        assert con_a.execute("SELECT * FROM t").fetchall() == (
            con_b.execute("SELECT * FROM t").fetchall()
        )
    finally:
        con_a.close()
        con_b.close()


def test_frame_lazy_e_percorrido_sem_materializar_de_uma_vez(tmp_path: Path) -> None:
    parquet = tmp_path / "origem.parquet"
    _frame(250).write_parquet(parquet)
    db_path = tmp_path / "extrato.db"

    frames.write_sqlite(
        pl.scan_parquet(parquet), db_path=db_path, table="extrato", batch_rows=30
    )

    assert _linhas_no_banco(db_path, "extrato") == 250


def test_escrita_substitui_o_conteudo_anterior(tmp_path: Path) -> None:
    """O primeiro lote usa `replace`; sem isso, reexportar duplicaria tudo."""
    db_path = tmp_path / "extrato.db"
    frames.write_sqlite(_frame(120), db_path=db_path, table="t", batch_rows=50)
    frames.write_sqlite(_frame(40), db_path=db_path, table="t", batch_rows=50)

    assert _linhas_no_banco(db_path, "t") == 40


def test_frame_vazio_nao_deixa_banco_para_tras(tmp_path: Path) -> None:
    destino = frames.write_frame(
        _frame(0), output_dir=tmp_path, stem="vazio", format="sqlite"
    )

    assert destino is None
    assert not (tmp_path / "vazio.db").exists()


def test_frame_lazy_vazio_tambem_nao_deixa_banco(tmp_path: Path) -> None:
    parquet = tmp_path / "vazia.parquet"
    _frame(0).write_parquet(parquet)

    destino = frames.write_frame(
        pl.scan_parquet(parquet), output_dir=tmp_path, stem="vazio", format="sqlite"
    )

    assert destino is None
    assert not (tmp_path / "vazio.db").exists()
