"""Smoke opt-in do SISCAN em CSV (FTP real do DATASUS).

Desligado por padrão; ``GUARACI_SISCAN_SMOKE=1`` liga. Baixa o menor arquivo da
série (histopatológico de mama por paciente, 2013, 70 KB) pelo serviço inteiro.
"""

from __future__ import annotations

import os

import polars as pl
import pytest

from guaraci.services.downloads import DownloadService

SMOKE = os.environ.get("GUARACI_SISCAN_SMOKE") == "1"
pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(not SMOKE, reason="Set GUARACI_SISCAN_SMOKE=1 to enable the live FTP smoke"),
]


def test_live_menor_arquivo(tmp_path):
    result = DownloadService().run(
        "siscan_csv",
        output_dir=str(tmp_path),
        output_format="parquet",
        tabelas=["HISTO_MAMA_PACNT"],
        anos=["2013"],
    )
    exported = list(tmp_path.glob("siscan_csv_HISTO_MAMA_PACNT_2013.parquet"))
    assert exported, result
    frame = pl.read_parquet(exported[0])
    assert frame.columns[0] == "CO_SEQ_SISCAN_HISTO_MAMA_PACNT"
    assert {"CO_MUN_RESIDENCIA", "CO_PACIENTE", "CO_IDADE_PACIENTE"} <= set(frame.columns)
    assert frame.height > 400
    assert all(dtype == pl.String for dtype in frame.dtypes)
