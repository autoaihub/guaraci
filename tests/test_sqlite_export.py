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


def _frame_com_decimal() -> pl.DataFrame:
    """Reproduz a forma dos bancos anuais da SRAG, que trazem 21 colunas assim."""
    return pl.DataFrame(
        {
            "NU_IDADE_N": pl.Series([1, 45, 90], dtype=pl.Decimal(precision=3, scale=0)),
            "RAIOX_RES": pl.Series(
                ["1.5", "2.25", "3.0"], dtype=pl.Utf8
            ).str.to_decimal(),
            "SG_UF": ["SP", "RJ", "MG"],
        }
    )


def test_coluna_decimal_nao_aborta_a_exportacao(tmp_path: Path) -> None:
    """`decimal.Decimal` não tem adaptador no sqlite3 e derrubava a escrita."""
    db_path = tmp_path / "srag.db"

    frames.write_sqlite(_frame_com_decimal(), db_path=db_path, table="records")

    assert _linhas_no_banco(db_path, "records") == 3


def test_decimal_sem_casas_vira_inteiro_exato(tmp_path: Path) -> None:
    db_path = tmp_path / "srag.db"
    frames.write_sqlite(_frame_com_decimal(), db_path=db_path, table="records")

    con = sqlite3.connect(db_path)
    try:
        idades = [linha[0] for linha in con.execute("SELECT NU_IDADE_N FROM records")]
    finally:
        con.close()

    assert idades == [1, 45, 90]
    assert all(isinstance(valor, int) for valor in idades)


def test_decimal_com_casas_vira_ponto_flutuante(tmp_path: Path) -> None:
    """O SQLite não tem tipo decimal; float é o que ele oferece."""
    db_path = tmp_path / "srag.db"
    frames.write_sqlite(_frame_com_decimal(), db_path=db_path, table="records")

    con = sqlite3.connect(db_path)
    try:
        valores = [linha[0] for linha in con.execute("SELECT RAIOX_RES FROM records")]
    finally:
        con.close()

    assert valores == [1.5, 2.25, 3.0]


def test_sqlite_safe_nao_toca_em_frame_sem_decimal(tmp_path: Path) -> None:
    origem = _frame(4)
    assert frames.sqlite_safe(origem) is origem


def test_conversao_do_portal_para_sqlite_funciona_com_decimal(tmp_path: Path) -> None:
    """O caminho real das fontes de arquivo em lote (SRAG, SISAGUA)."""
    from guaraci.opendatasus.portal_files import PortalFileDataSource

    origem = tmp_path / "INFLUD.parquet"
    _frame_com_decimal().write_parquet(origem)
    ds = PortalFileDataSource(output_path=str(tmp_path))

    destino = ds._convert_to_format(origem, "sqlite")

    assert destino.exists()
    assert _linhas_no_banco(destino, "records") == 3


@pytest.mark.parametrize(
    "modulo, classe, tabela",
    [
        ("guaraci.ana.hidro", "AnaHidroDataSource", "ana_hidro_records"),
        ("guaraci.inmet.datasource", "InmetEstacoesDataSource", "inmet_estacoes_records"),
    ],
)
def test_exports_sqlite_das_demais_fontes_gravam_o_arquivo(
    tmp_path: Path, modulo: str, classe: str, tabela: str
) -> None:
    """Os quatro caminhos sqlite do repo passam pelo mesmo escritor em lotes."""
    import importlib

    ds = getattr(importlib.import_module(modulo), classe)(output_path=str(tmp_path))

    destino = ds.export(_frame_com_decimal(), format="sqlite", name="extrato")

    assert destino.exists()
    assert _linhas_no_banco(destino, tabela) == 3
