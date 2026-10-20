"""Smoke opt-in das fontes ambientais de arquivo HTTP (rede real).

Desligado por padrão; ``GUARACI_ARQUIVOS_SMOKE=1`` liga. A área queimada baixa o
arquivo inteiro (13 KB). O SISAM só baixa com ``GUARACI_SISAM_SMOKE=1``, pois o ano mais
leve (2018) tem 136 MB comprimidos e ~590 MB de CSV.
"""

from __future__ import annotations

import os

import polars as pl
import pytest

from guaraci.arquivos import HTTP_FILES, HttpFileClient, HttpFileDataSource

SMOKE = os.environ.get("GUARACI_ARQUIVOS_SMOKE") == "1"
SISAM = os.environ.get("GUARACI_SISAM_SMOKE") == "1"
pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        not SMOKE, reason="Set GUARACI_ARQUIVOS_SMOKE=1 to enable the live file smoke test"
    ),
]


def test_live_area_queimada_inteira(tmp_path):
    key = "inpe_area_queimada_biomas"
    payload = HttpFileDataSource(output_path=str(tmp_path), dataset=key).download(
        output_dir=str(tmp_path), output_format="csv"
    )
    frame = pl.read_csv(payload["exported_files"][0], infer_schema=False)
    assert frame.columns[:2] == ["Ano", "Mês"]
    assert "Total mensal" in frame.columns
    assert frame["Ano"][0] == "2002" and frame["Mês"][0] == "09"




def test_live_sisam_so_head():
    remote = HttpFileClient(timeout_seconds=60).head(HTTP_FILES["inpe_sisam"].resources[0].url)
    assert remote.size and remote.size > 100_000_000


@pytest.mark.skipif(not SISAM, reason="Set GUARACI_SISAM_SMOKE=1 to download SISAM 2018")
def test_live_sisam_2018(tmp_path):
    payload = HttpFileDataSource(output_path=str(tmp_path), dataset="inpe_sisam").download(
        output_dir=str(tmp_path), output_format="parquet", anos=[2018]
    )
    assert payload["failed_count"] == 0
    frame = pl.scan_parquet(payload["exported_files"][0])
    assert {"datahora", "municipio_nome", "pm25_ugm3", "o3_ppb"} <= set(
        frame.collect_schema().names()
    )
    assert frame.select(pl.len()).collect().item() > 5_000_000
