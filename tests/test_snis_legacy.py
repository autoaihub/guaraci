"""
Tests for legacy SNIS BigQuery helper utilities.
"""

import pytest

from guaraci.snis.legacy.bigquery import SnisLegacyBigQueryDataSource


def test_parse_table_id_valid():
    project, dataset, table = SnisLegacyBigQueryDataSource._parse_table_id(
        "basedosdados.br_mdr_snis.municipio_agua_esgoto"
    )
    assert project == "basedosdados"
    assert dataset == "br_mdr_snis"
    assert table == "municipio_agua_esgoto"


def test_parse_table_id_invalid():
    with pytest.raises(ValueError):
        SnisLegacyBigQueryDataSource._parse_table_id("invalid")


def test_pick_field_with_normalized_names():
    ds = SnisLegacyBigQueryDataSource(output_path="data/test_snis")
    fields = ["ANO_REFERENCIA", "id-municipio-ibge", "SIGLA UF"]

    assert ds._pick_field(fields, ds.ANO_CANDIDATES) == "ANO_REFERENCIA"
    assert ds._pick_field(fields, ds.MUNICIPIO_CANDIDATES) == "id-municipio-ibge"
    assert ds._pick_field(fields, ds.UF_CANDIDATES) == "SIGLA UF"


def test_resolve_indicator_columns_uses_aliases():
    ds = SnisLegacyBigQueryDataSource(output_path="data/test_snis")
    fields = [
        "populacao_atendida_agua",
        "volume_esgoto_tratado",
        "populacao_urbana_residente_agua",
    ]

    resolved = ds._resolve_indicator_columns(fields)

    assert resolved["AG001"] == "populacao_atendida_agua"
    assert resolved["ES006"] == "volume_esgoto_tratado"
    assert resolved["G06A"] == "populacao_urbana_residente_agua"
    assert resolved["AG001A"] is None


def test_clean_filters_validation():
    assert SnisLegacyBigQueryDataSource._clean_ufs(["sp", "RJ"]) == ["SP", "RJ"]
    assert SnisLegacyBigQueryDataSource._clean_municipios(["3550308", "3304557"]) == [
        "3550308",
        "3304557",
    ]

    with pytest.raises(ValueError):
        SnisLegacyBigQueryDataSource._clean_ufs(["SPO"])

    with pytest.raises(ValueError):
        SnisLegacyBigQueryDataSource._clean_municipios(["35503A8"])


def test_build_sql_selects_aliases_and_filters(monkeypatch):
    ds = SnisLegacyBigQueryDataSource(output_path="data/test_snis")
    monkeypatch.setattr(
        ds,
        "OUTPUT_COLUMNS",
        ["id_municipio", "ano", "AG001", "G06A"],
        raising=False,
    )

    sql = ds._build_sql(
        table_ref="basedosdados.br_mdr_snis.municipio_agua_esgoto",
        ano=2023,
        ano_col="ano_referencia",
        municipio_col="id_municipio_ibge",
        uf_col="sigla_uf",
        resolved_columns={"AG001": "populacao_atendida_agua", "G06A": None},
        ufs=["sp", "rj"],
        municipios=["3550308"],
        extra_fields=["prestador_nome"],
    )

    assert "`ano_referencia` AS `ano`" in sql
    assert "`id_municipio_ibge` AS `id_municipio`" in sql
    assert "`populacao_atendida_agua` AS `AG001`" in sql
    assert "NULL AS `G06A`" in sql
    assert "`prestador_nome`" in sql
    assert "`ano_referencia` = 2023" in sql
    assert "`sigla_uf` IN ('SP', 'RJ')" in sql
    assert "`id_municipio_ibge` IN ('3550308')" in sql
