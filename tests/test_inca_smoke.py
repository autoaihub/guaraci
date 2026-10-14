"""Smoke opt-in do Integrador RHC do INCA (rede real); ``GUARACI_INCA_SMOKE=1`` liga.

Baixa um ano (2023, cerca de 5 MB de zip) e confere as 46 colunas do DBF.
"""

from __future__ import annotations

import os

import polars as pl
import pytest

from guaraci.inca import datasource_for

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        os.environ.get("GUARACI_INCA_SMOKE") != "1",
        reason="Set GUARACI_INCA_SMOKE=1 to enable the live INCA smoke test",
    ),
]


def test_live_2023_rhc(tmp_path):
    payload = datasource_for("inca_rhc")(str(tmp_path)).download(
        start_year=2023, output_format="parquet", output_dir=str(tmp_path)
    )
    assert payload["failed_count"] == 0
    frame = pl.read_parquet(payload["exported_files"][0])
    assert frame.width == 46
    assert frame.height > 50_000
    assert {"SEXO", "IDADE", "CNES", "MUUH", "UFUH", "DTDIAGNO", "TNM"} <= set(frame.columns)
