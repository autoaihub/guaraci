"""Opt-in live smoke test for the IBGE connector (real SIDRA API).

Disabled by default; set ``GUARACI_IBGE_SMOKE=1`` to run. Fetches Brazil's total
population estimate for one year (a single-locality, keyless GET) and asserts a
sane value — validating the live SIDRA URL and response parsing.
"""
from __future__ import annotations

import os

import pytest

from guaraci.ibge import IbgePopulacaoDataSource

SMOKE = os.environ.get("GUARACI_IBGE_SMOKE") == "1"
pytestmark = pytest.mark.skipif(
    not SMOKE, reason="Set GUARACI_IBGE_SMOKE=1 to enable the live IBGE smoke test"
)


def test_live_brazil_population(tmp_path):
    ds = IbgePopulacaoDataSource(output_path=str(tmp_path))
    payload = ds.download(start_year=2021, end_year=2021, level="brasil")
    assert payload["documents_found"] >= 1
    row = ds.load_dataframe().row(0, named=True)
    assert row["localidade_nome"] == "Brasil"
    assert row["ano"] == 2021
    assert 150_000_000 < row["valor"] < 260_000_000  # sane BR population
