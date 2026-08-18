"""Opt-in live smoke test for the INPE Queimadas connector (real file server).

Disabled by default; set ``GUARACI_INPE_SMOKE=1`` to run. Downloads a SINGLE
year (the smallest recorded, 2003) of the reference annual product and
asserts a sane shape - validating the live directory listing and the ZIP/CSV
parsing against the real upstream data.
"""
from __future__ import annotations

import os

import pytest

from guaraci.inpe.queimadas import InpeQueimadasDataSource

SMOKE = os.environ.get("GUARACI_INPE_SMOKE") == "1"
pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        not SMOKE, reason="Set GUARACI_INPE_SMOKE=1 to enable the live INPE smoke test"
    ),
]


def test_live_annual_reference_2003(tmp_path):
    ds = InpeQueimadasDataSource(output_path=str(tmp_path))
    payload = ds.download(start_year=2003, end_year=2003)
    assert payload["documents_found"] > 100_000  # 2003 has ~341k detections
    df = ds.load_dataframe()
    assert {"lat", "lon", "estado", "municipio", "bioma"} <= set(df.columns)
    assert df["lat"].dtype.is_numeric()
    assert set(df["estado"].unique().to_list()) <= {
        "ACRE", "ALAGOAS", "AMAPÁ", "AMAZONAS", "BAHIA", "CEARÁ",
        "DISTRITO FEDERAL", "ESPÍRITO SANTO", "GOIÁS", "MARANHÃO",
        "MATO GROSSO", "MATO GROSSO DO SUL", "MINAS GERAIS", "PARÁ",
        "PARAÍBA", "PARANÁ", "PERNAMBUCO", "PIAUÍ", "RIO DE JANEIRO",
        "RIO GRANDE DO NORTE", "RIO GRANDE DO SUL", "RONDÔNIA", "RORAIMA",
        "SANTA CATARINA", "SÃO PAULO", "SERGIPE", "TOCANTINS",
    }


def test_live_states_filter(tmp_path):
    ds = InpeQueimadasDataSource(output_path=str(tmp_path))
    payload = ds.download(start_year=2003, end_year=2003, states=["AC"])
    assert payload["documents_found"] > 0
    df = ds.load_dataframe()
    assert set(df["estado"].unique().to_list()) == {"ACRE"}
