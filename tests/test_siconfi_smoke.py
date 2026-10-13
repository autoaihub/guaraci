"""Smoke ao vivo do SICONFI. Opt-in: ``GUARACI_SICONFI_SMOKE=1``."""

from __future__ import annotations

import os

import polars as pl
import pytest

from guaraci.tesouro import SiconfiDcaDespesaFuncaoDataSource

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        os.environ.get("GUARACI_SICONFI_SMOKE") != "1",
        reason="Set GUARACI_SICONFI_SMOKE=1 to enable the live SICONFI smoke test",
    ),
]


def test_live_sao_paulo_saude_2023(tmp_path):
    source = SiconfiDcaDespesaFuncaoDataSource(output_path=str(tmp_path))
    result = source.download(start_year=2023, entes=["3550308"], output_dir=str(tmp_path))
    assert result["failed_count"] == 0
    frame = pl.read_csv(result["exported_files"][0], infer_schema=False)
    assert frame.height > 0
    assert frame["conta"].str.starts_with("10").all()
    assert "10 - Saúde" in frame["conta"].to_list()
