"""Smoke ao vivo do WFS (FUNAI e SGB), opt-in com GUARACI_GEO_SMOKE=1."""

from __future__ import annotations

import os

import polars as pl
import pytest

from guaraci.geo import WfsDataSource

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        os.environ.get("GUARACI_GEO_SMOKE") != "1",
        reason="Set GUARACI_GEO_SMOKE=1 to enable the live WFS smoke test",
    ),
]


def test_funai_aldeias_live(tmp_path):
    result = WfsDataSource("funai_aldeias", output_path=str(tmp_path)).download(
        output_dir=str(tmp_path), page_size=1500
    )
    assert result["failed_count"] == 0
    frame = pl.read_csv(result["exported_files"][0], infer_schema=False)
    assert frame.height > 4000
    assert frame["the_geom"][0].startswith("POINT (-")  # lon lat, versão 1.0.0


def test_sgb_risco_rondonia_live(tmp_path):
    result = WfsDataSource("sgb_risco_geologico", output_path=str(tmp_path)).download(
        output_dir=str(tmp_path), cql_filter="uf='RO'", page_size=100
    )
    assert result["failed_count"] == 0
    frame = pl.read_csv(result["exported_files"][0], infer_schema=False)
    assert frame.height > 0 and set(frame["uf"].to_list()) == {"RO"}
    assert result["export_warning"] is None
