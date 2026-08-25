"""Opt-in live smoke test for the IBGE connector (real SIDRA API).

Disabled by default; set ``GUARACI_IBGE_SMOKE=1`` to run. Fetches Brazil's total
population estimate for one year (a single-locality, keyless GET) and asserts a
sane value — validating the live SIDRA URL and response parsing.
"""
from __future__ import annotations

import os

import pytest

from guaraci.ibge import (
    IbgeAreaTerritorialDataSource,
    IbgeCasamentosDataSource,
    IbgeDivorciosDataSource,
    IbgeNascidosVivosRcDataSource,
    IbgeObitosRcDataSource,
    IbgePibMunicipiosDataSource,
    IbgePopulacaoDataSource,
    IbgePopulacaoIdadeSexoDataSource,
    IbgeSaneamentoAguaDataSource,
    IbgeSaneamentoEsgotoDataSource,
    IbgeSaneamentoLixoDataSource,
)

SMOKE = os.environ.get("GUARACI_IBGE_SMOKE") == "1"
pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
    not SMOKE, reason="Set GUARACI_IBGE_SMOKE=1 to enable the live IBGE smoke test"
),
]


def test_live_brazil_population(tmp_path):
    ds = IbgePopulacaoDataSource(output_path=str(tmp_path))
    payload = ds.download(start_year=2021, end_year=2021, level="brasil")
    assert payload["documents_found"] >= 1
    row = ds.load_dataframe().row(0, named=True)
    assert row["localidade_nome"] == "Brasil"
    assert row["ano"] == 2021
    assert 150_000_000 < row["valor"] < 260_000_000  # sane BR population


def test_live_brazil_pib(tmp_path):
    ds = IbgePibMunicipiosDataSource(output_path=str(tmp_path))
    ds.download(start_year=2021, end_year=2021, level="brasil")
    row = ds.load_dataframe().row(0, named=True)
    assert row["localidade_nome"] == "Brasil"
    assert row["valor"] > 5_000_000_000  # BR GDP 2021 > R$ 5 trillion (Mil Reais)


def test_live_population_by_sex_age(tmp_path):
    ds = IbgePopulacaoIdadeSexoDataSource(output_path=str(tmp_path))
    ds.download(start_year=2022, end_year=2022, level="brasil", sexo="ambos", faixa_etaria="quinquenal")
    df = ds.load_dataframe()
    assert {"sexo", "idade"} <= set(df.columns)
    assert set(df["sexo"].to_list()) == {"Homens", "Mulheres"}
    assert df["valor"].sum() > 150_000_000  # summed age groups ~ total pop


def test_live_nascidos_vivos_rc_brazil_2023(tmp_path):
    # Reference verified live 2026-08-17: Brasil, 2023, mes/sexo=Total -> 2 523 267.
    ds = IbgeNascidosVivosRcDataSource(output_path=str(tmp_path))
    ds.download(start_year=2023, end_year=2023, level="brasil")
    row = ds.load_dataframe().row(0, named=True)
    assert row["localidade_nome"] == "Brasil"
    assert row["valor"] == 2_523_267


def test_live_obitos_rc_brazil_2023(tmp_path):
    # Reference verified live 2026-08-17: Brasil, 2023, mes/sexo=Total -> 1 429 575.
    ds = IbgeObitosRcDataSource(output_path=str(tmp_path))
    ds.download(start_year=2023, end_year=2023, level="brasil")
    row = ds.load_dataframe().row(0, named=True)
    assert row["localidade_nome"] == "Brasil"
    assert row["valor"] == 1_429_575


def test_live_area_territorial_brazil(tmp_path):
    # Reference verified live 2026-08-17: Brasil, 2022 -> 8 510 417.771 km².
    ds = IbgeAreaTerritorialDataSource(output_path=str(tmp_path))
    ds.download(level="brasil")
    df = ds.load_dataframe()
    area_row = df.filter(df["variavel_id"] == "6318").row(0, named=True)
    assert area_row["localidade_nome"] == "Brasil"
    assert area_row["valor"] == pytest.approx(8_510_417.771, abs=1.0)


def test_live_casamentos_brazil_2023(tmp_path):
    # Reference verified live 2026-08-25: Brasil, 2023, mes=Total -> 940 799.
    ds = IbgeCasamentosDataSource(output_path=str(tmp_path))
    ds.download(start_year=2023, end_year=2023, level="brasil")
    row = ds.load_dataframe().row(0, named=True)
    assert row["localidade_nome"] == "Brasil"
    assert row["valor"] == 940_799


def test_live_divorcios_brazil_2023(tmp_path):
    # Reference verified live 2026-08-25: Brasil, 2023, todas classificacoes
    # em Total -> 360 787.
    ds = IbgeDivorciosDataSource(output_path=str(tmp_path))
    ds.download(start_year=2023, end_year=2023, level="brasil")
    row = ds.load_dataframe().row(0, named=True)
    assert row["localidade_nome"] == "Brasil"
    assert row["valor"] == 360_787


def test_live_saneamento_agua_brazil_2022(tmp_path):
    # Reference verified live 2026-08-25: Brasil, 2022, detalhe=total ->
    # 72 456 368 domicilios.
    ds = IbgeSaneamentoAguaDataSource(output_path=str(tmp_path))
    ds.download(level="brasil")
    row = ds.load_dataframe().row(0, named=True)
    assert row["localidade_nome"] == "Brasil"
    assert row["valor"] == 72_456_368


def test_live_saneamento_esgoto_brazil_2022(tmp_path):
    # Reference verified live 2026-08-25: Brasil, 2022, detalhe=total ->
    # 72 456 368 domicilios.
    ds = IbgeSaneamentoEsgotoDataSource(output_path=str(tmp_path))
    ds.download(level="brasil")
    row = ds.load_dataframe().row(0, named=True)
    assert row["localidade_nome"] == "Brasil"
    assert row["valor"] == 72_456_368


def test_live_saneamento_lixo_brazil_2022(tmp_path):
    # Reference verified live 2026-08-25: Brasil, 2022, detalhe=total ->
    # 72 456 368 domicilios.
    ds = IbgeSaneamentoLixoDataSource(output_path=str(tmp_path))
    ds.download(level="brasil")
    row = ds.load_dataframe().row(0, named=True)
    assert row["localidade_nome"] == "Brasil"
    assert row["valor"] == 72_456_368
