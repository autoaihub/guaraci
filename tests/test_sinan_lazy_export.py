"""Regressões do processamento pós-download do SINAN.

Cobrem a troca do ``map_elements`` linha a linha por expressão nativa no
mapeamento de UF e o caminho de exportação em streaming, que existe para
que uma doença com muitos anos não precise caber inteira na memória.
"""

from __future__ import annotations

import polars as pl
import pytest

from guaraci.datasus import filtering
from guaraci.datasus.sinan import SinanDataSource


@pytest.fixture
def source_with_years(tmp_path):
    """Datasource apontando para dois parquets anuais com colunas diferentes."""
    ds = SinanDataSource(output_path=str(tmp_path))

    ano_2023 = tmp_path / "DENGBR23.parquet"
    pl.DataFrame(
        {
            "NU_ANO": ["2023", "2023"],
            "SG_UF_NOT": ["35", "33"],
            "CS_SEXO": ["M", "F"],
        }
    ).write_parquet(ano_2023)

    # O formulário muda entre anos: 2024 traz uma coluna a mais.
    ano_2024 = tmp_path / "DENGBR24.parquet"
    pl.DataFrame(
        {
            "NU_ANO": ["2024"],
            "SG_UF_NOT": ["SP"],
            "CS_SEXO": ["F"],
            "COLUNA_NOVA": ["x"],
        }
    ).write_parquet(ano_2024)

    ds.data["DENG"] = [str(ano_2023), str(ano_2024)]
    return ds


def test_scan_dataframe_is_lazy(source_with_years) -> None:
    assert isinstance(source_with_years.scan_dataframe("DENG"), pl.LazyFrame)


def test_scan_reconciles_years_with_different_columns(source_with_years) -> None:
    df = source_with_years.scan_dataframe("DENG").collect()
    assert df.height == 3
    assert "COLUNA_NOVA" in df.columns


def test_uf_mapping_resolves_codes_and_siglas(source_with_years) -> None:
    df = source_with_years.scan_dataframe("DENG").collect()
    assert sorted(df["SG_UF_NOT"].to_list()) == ["RJ", "SP", "SP"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("35", "SP"),
        ("sp", "SP"),
        (" 35 ", "SP"),
        ("35.0", "SP"),
        ("0", None),
        ("", None),
        ("99", None),
        (None, None),
    ],
)
def test_uf_mapping_expression_handles_sentinels(raw, expected) -> None:
    # A coluna precisa ter ao menos uma UF reconhecível, senão é preservada
    # intacta por ser considerada um campo que não guarda UF.
    df = pl.DataFrame({"SG_UF": [raw, "35"]}, schema={"SG_UF": pl.Utf8})
    result = df.with_columns([filtering.uf_normalization_expr(df, "SG_UF")])
    assert result["SG_UF"].to_list()[0] == expected


def test_export_streams_lazyframe_to_parquet(source_with_years, tmp_path) -> None:
    lf = source_with_years.scan_dataframe("DENG")
    path = source_with_years.export(lf, format="parquet", name="DENG_2023_2024")

    assert path is not None and path.exists()
    assert pl.read_parquet(path).height == 3


def test_export_streams_lazyframe_to_csv(source_with_years) -> None:
    lf = source_with_years.scan_dataframe("DENG")
    path = source_with_years.export(lf, format="csv", name="DENG_2023_2024")

    assert path is not None and path.exists()
    assert pl.read_csv(path).height == 3


def test_export_still_accepts_eager_dataframe(source_with_years) -> None:
    df = source_with_years.load_dataframe("DENG")
    assert isinstance(df, pl.DataFrame)

    path = source_with_years.export(df, format="parquet", name="DENG_2023_2024")
    assert path is not None and path.exists()


def test_export_flags_incomplete_year_range(source_with_years) -> None:
    """O sufixo _partial continua sinalizando cobertura menor que a pedida."""
    lf = source_with_years.scan_dataframe("DENG")
    path = source_with_years.export(lf, format="parquet", name="DENG_2014_2024")

    assert path is not None
    assert path.stem == "DENG_2014_2024_partial"


def test_filter_works_on_lazy_plan(source_with_years) -> None:
    lf = source_with_years.scan_dataframe("DENG")
    filtered = source_with_years.filter(lf, uf="SP").collect()

    assert filtered.height == 2
    assert set(filtered["SG_UF_NOT"].to_list()) == {"SP"}
