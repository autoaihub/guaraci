"""Regressões dos filtros de refinamento de SIH, SIM e SINAN.

Cada caso aqui corresponde a um filtro que, contra microdados reais do
DATASUS, devolvia o conjunto errado ou morria. Os valores usados nas
asserções foram conferidos nos arquivos publicados (dengue nacional
2014-2024, SIM CID10 AC 2020 e SIH RD AC 2023-01).
"""

from __future__ import annotations

import polars as pl
import pytest

from guaraci.datasus import filtering
from guaraci.datasus.sih import SihDataSource
from guaraci.datasus.sim import SimDataSource
from guaraci.datasus.sinan import SinanDataSource


# --- escolha de coluna -------------------------------------------------------


def test_resolve_skips_column_that_exists_but_is_empty() -> None:
    """O SINAN traz ``UF`` vazia e ``SG_UF_NOT`` preenchida.

    Filtrar pela primeira coluna existente devolvia 103 059 dos 5 047 004
    casos de São Paulo, sem sinal de erro.
    """
    df = pl.DataFrame(
        {
            "UF": [None, None, None],
            "SG_UF_NOT": ["35", "35", "33"],
        }
    )
    assert filtering.resolve_filter_column(df, ["UF", "SG_UF_NOT"]) == "SG_UF_NOT"


def test_resolve_treats_blank_strings_as_empty() -> None:
    df = pl.DataFrame({"UF": ["", "  ", ""], "SG_UF": ["SP", "RJ", "MG"]})
    assert filtering.resolve_filter_column(df, ["UF", "SG_UF"]) == "SG_UF"


def test_resolve_keeps_declared_preference_when_data_exists() -> None:
    df = pl.DataFrame({"UF": ["SP"], "SG_UF": ["RJ"]})
    assert filtering.resolve_filter_column(df, ["UF", "SG_UF"]) == "UF"


def test_resolve_returns_none_when_no_candidate_exists() -> None:
    df = pl.DataFrame({"OUTRA": [1]})
    assert filtering.resolve_filter_column(df, ["UF", "SG_UF"]) is None


def test_resolve_falls_back_to_first_when_all_candidates_are_empty() -> None:
    df = pl.DataFrame({"UF": [None], "SG_UF": [None]})
    assert filtering.resolve_filter_column(df, ["UF", "SG_UF"]) == "UF"


# --- comparação com tipos diferentes ----------------------------------------


@pytest.mark.parametrize(
    ("column_values", "dtype", "value"),
    [
        ([4023, 4024], pl.Int64, "4023"),  # NU_IDADE_N é Int64, CLI manda texto
        (["2020", "2021"], pl.Utf8, 2020),  # NU_ANO é texto, CLI manda inteiro
        (["01", "02"], pl.Utf8, 1),  # MES_CMPT tem zero à esquerda
        ([35.0, 33.0], pl.Float64, "35"),  # coluna lida como float
    ],
)
def test_equality_matches_across_types(column_values, dtype, value) -> None:
    """Antes, cada um destes derrubava o filtro com ComputeError."""
    df = pl.DataFrame({"COL": column_values}, schema={"COL": dtype})
    result = df.filter(filtering.equality_expr(df, "COL", value))
    assert result.height == 1


def test_equality_is_case_insensitive_for_text() -> None:
    df = pl.DataFrame({"COL": ["SP", "RJ"]})
    assert df.filter(filtering.equality_expr(df, "COL", "sp")).height == 1


# --- UF em suas várias representações ---------------------------------------


@pytest.mark.parametrize(
    ("stored", "pedido", "esperado"),
    [
        (["SP", "RJ"], "SP", 1),  # sigla, como no SINAN
        (["35", "33"], "SP", 1),  # código IBGE de dois dígitos
        (["120000", "350000"], "AC", 1),  # UF_ZI do SIH, código do gestor
        (["120040", "355030"], "SP", 1),  # CODMUNRES do SIM, código municipal
        (["120040", "355030"], "35", 1),  # usuário informa o código
        (["120040", "355030"], "ZZ", 0),  # UF inexistente não casa nada
    ],
)
def test_uf_expr_reads_every_representation(stored, pedido, esperado) -> None:
    df = pl.DataFrame({"COL": stored})
    assert df.filter(filtering.uf_expr(df, "COL", pedido)).height == esperado


# --- normalização de UF sem destruir colunas homônimas ----------------------


def test_uf_normalization_preserves_column_that_is_not_uf() -> None:
    """``UF_ZI`` (120000) e ``GRAV_INSUF`` (clínica) casavam o filtro por nome.

    Como nenhum valor delas corresponde a uma UF, o mapeamento antigo
    substituía a coluna inteira por nulo e o dado sumia do arquivo exportado.
    """
    df = pl.DataFrame({"UF_ZI": ["120000", "120000"], "GRAV_INSUF": ["1", "2"]})
    result = df.with_columns(
        [
            filtering.uf_normalization_expr(df, "UF_ZI"),
            filtering.uf_normalization_expr(df, "GRAV_INSUF"),
        ]
    )
    assert result["UF_ZI"].to_list() == ["120000", "120000"]
    assert result["GRAV_INSUF"].to_list() == ["1", "2"]


def test_uf_normalization_still_maps_real_uf_columns() -> None:
    df = pl.DataFrame({"SG_UF_NOT": ["35", "33", "", "99"]})
    result = df.with_columns([filtering.uf_normalization_expr(df, "SG_UF_NOT")])
    assert result["SG_UF_NOT"].to_list() == ["SP", "RJ", None, None]


def test_uf_column_names_matches_by_name() -> None:
    nomes = ["SG_UF_NOT", "UF_ZI", "GRAV_INSUF", "CS_SEXO", "COUFINF"]
    assert filtering.uf_column_names(nomes) == [
        "SG_UF_NOT",
        "UF_ZI",
        "GRAV_INSUF",
        "COUFINF",
    ]


# --- código por rótulo (sexo) ------------------------------------------------


def test_sim_and_sih_encode_sex_differently() -> None:
    """A interface expõe M/F; o SIM grava 1/2 e o SIH grava 1/3."""
    assert SimDataSource.SEXO_CODES["F"] == "2"
    assert SihDataSource.SEXO_CODES["F"] == "3"


def test_coded_equality_translates_label_to_code() -> None:
    df = pl.DataFrame({"SEXO": ["1", "2", "1"]})
    expr = filtering.coded_equality_expr(df, "SEXO", "M", SimDataSource.SEXO_CODES)
    assert df.filter(expr).height == 2


def test_coded_equality_accepts_the_raw_code_too() -> None:
    df = pl.DataFrame({"SEXO": ["1", "2"]})
    expr = filtering.coded_equality_expr(df, "SEXO", "2", SimDataSource.SEXO_CODES)
    assert df.filter(expr).height == 1


# --- filtros de ponta a ponta em cada datasource -----------------------------


def test_sinan_uf_filter_uses_the_populated_column() -> None:
    ds = SinanDataSource(output_path=".")
    df = pl.DataFrame(
        {
            "UF": [None, None, None],
            "SG_UF_NOT": ["SP", "SP", "RJ"],
            "CS_SEXO": ["F", "M", "F"],
        }
    )
    assert ds.filter(df, uf="SP").height == 2


@pytest.mark.parametrize(
    ("kwargs", "esperado"),
    [
        ({"uf": "SP"}, 2),
        ({"sexo": "F"}, 2),
        ({"ano": 2020}, 2),
        ({"faixa_etaria": 4023}, 2),
        ({"uf": "SP", "sexo": "F"}, 1),
        ({"uf": "ZZ"}, 0),
    ],
)
def test_sinan_filters_end_to_end(kwargs, esperado) -> None:
    ds = SinanDataSource(output_path=".")
    df = pl.DataFrame(
        {
            "SG_UF_NOT": ["SP", "SP", "RJ"],
            "CS_SEXO": ["F", "M", "F"],
            "NU_ANO": ["2020", "2020", "2021"],
            "NU_IDADE_N": [4023, 4030, 4023],
        }
    )
    assert ds.filter(df, **kwargs).height == esperado


def test_sim_uf_filter_reads_the_municipality_code() -> None:
    """Nos arquivos do SIM não há coluna de UF: ela vive no código do município.

    Nenhum candidato existia, e o filtro era descartado em silêncio, de modo
    que quem pedia um estado recebia o país inteiro.
    """
    ds = SimDataSource(output_path=".")
    df = pl.DataFrame({"CODMUNRES": ["120040", "120020", "355030"]})
    assert ds.filter(df, uf="AC").height == 2
    assert ds.filter(df, uf="SP").height == 1


def test_sim_year_filter_reads_the_last_four_digits_of_dtobito() -> None:
    """DTOBITO é DDMMAAAA; o recorte antigo pegava DDMM e nunca casava."""
    ds = SimDataSource(output_path=".")
    df = pl.DataFrame({"DTOBITO": ["22052020", "06062020", "15031999"]})
    assert ds.filter(df, ano_obito=2020).height == 2
    assert ds.filter(df, ano_obito=1999).height == 1


def test_sim_sex_filter_translates_to_the_system_code() -> None:
    ds = SimDataSource(output_path=".")
    df = pl.DataFrame({"SEXO": ["1", "2", "1", "0"]})
    assert ds.filter(df, sexo="M").height == 2
    assert ds.filter(df, sexo="F").height == 1


def test_sih_uf_filter_reads_the_manager_code() -> None:
    ds = SihDataSource(output_path=".")
    df = pl.DataFrame({"UF_ZI": ["120000", "120000", "350000"]})
    assert ds.filter(df, uf="AC").height == 2
    assert ds.filter(df, uf="SP").height == 1


def test_sih_sex_filter_uses_one_and_three() -> None:
    ds = SihDataSource(output_path=".")
    df = pl.DataFrame({"SEXO": ["1", "3", "3"]})
    assert ds.filter(df, sexo="M").height == 1
    assert ds.filter(df, sexo="F").height == 2


def test_sih_month_filter_matches_zero_padded_values() -> None:
    ds = SihDataSource(output_path=".")
    df = pl.DataFrame({"MES_CMPT": ["01", "02", "01"], "ANO_CMPT": ["2023"] * 3})
    assert ds.filter(df, mes=1).height == 2
    assert ds.filter(df, mes="01").height == 2
    assert ds.filter(df, ano=2023).height == 3


def test_sih_cid_filter_matches_by_prefix() -> None:
    ds = SihDataSource(output_path=".")
    df = pl.DataFrame({"DIAG_PRINC": ["O800", "O809", "K800"]})
    assert ds.filter(df, cid="O80").height == 2
    assert ds.filter(df, cid="o80").height == 2


def test_filters_without_arguments_return_everything() -> None:
    df = pl.DataFrame({"SG_UF_NOT": ["SP", "RJ"]})
    assert SinanDataSource(output_path=".").filter(df).height == 2


def test_empty_string_filter_is_ignored() -> None:
    """Um valor em branco vindo do formulário não pode zerar o resultado."""
    df = pl.DataFrame({"SG_UF_NOT": ["SP", "RJ"]})
    assert SinanDataSource(output_path=".").filter(df, uf="").height == 2


def test_filters_work_the_same_on_a_lazy_plan() -> None:
    df = pl.DataFrame(
        {"SG_UF_NOT": ["SP", "SP", "RJ"], "CS_SEXO": ["F", "M", "F"]}
    )
    ds = SinanDataSource(output_path=".")
    eager = ds.filter(df, uf="SP").height
    lazy = ds.filter(df.lazy(), uf="SP").collect().height
    assert eager == lazy == 2
