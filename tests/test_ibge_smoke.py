"""Opt-in live smoke test for the IBGE connector (real SIDRA API).

Disabled by default; set ``GUARACI_IBGE_SMOKE=1`` to run. Fetches Brazil's total
population estimate for one year (a single-locality, keyless GET) and asserts a
sane value — validating the live SIDRA URL and response parsing.
"""
from __future__ import annotations

import os

import pytest

from guaraci.ibge import (
    IbgePibMunicipiosDataSource,
    IbgePopulacaoDataSource,
    IbgePopulacaoIdadeSexoDataSource,
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
