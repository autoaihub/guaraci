"""Opt-in live smoke test for the INMET connector (real portal.inmet.gov.br).

Disabled by default; set ``GUARACI_INMET_SMOKE=1`` to run. Downloads ONE
recent year's full ZIP (~90 MB as of 2026-08-18 for 2025; the current year is
smaller while partial) but extracts/parses only ONE UF, per the "smoke uses 1
year + 1 UF" rule for this source (the plan explicitly forbids downloading
every UF in the agent loop).
"""
from __future__ import annotations

import os

import pytest

from guaraci.inmet import InmetEstacoesDataSource

SMOKE = os.environ.get("GUARACI_INMET_SMOKE") == "1"
pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        not SMOKE, reason="Set GUARACI_INMET_SMOKE=1 to enable the live INMET smoke test"
    ),
]


def test_live_one_year_one_uf(tmp_path):
    ds = InmetEstacoesDataSource(output_path=str(tmp_path))
    payload = ds.download(start_year=2025, end_year=2025, ufs=["DF"], output_format="csv")

    assert payload["record_count"] > 0
    assert payload["station_count"] >= 1
    df = ds.load_dataframe()
    assert set(df["uf"].unique().to_list()) == {"DF"}
    assert df["latitude"].drop_nulls().is_not_null().all()
    # Hourly automatic-station data: no more than 366*24 rows per station/year.
    assert df.height <= payload["station_count"] * 366 * 24
