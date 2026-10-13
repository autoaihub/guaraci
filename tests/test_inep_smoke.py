"""Smoke opt-in do Censo Escolar INEP (rede real); ``GUARACI_INEP_SMOKE=1`` liga.

Faz HEAD de 2007, 2024 e 2025 e baixa só o zip de 2007 (o menor da série com o
esquema atual) para conferir o CSV de escolas.
"""

from __future__ import annotations

import os

import polars as pl
import pytest

from guaraci.arquivos import HttpFileClient
from guaraci.arquivos.inep_censo_escolar import InepCensoEscolarDataSource, year_url

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        os.environ.get("GUARACI_INEP_SMOKE") != "1",
        reason="Set GUARACI_INEP_SMOKE=1 to enable the live INEP smoke test",
    ),
]


@pytest.mark.parametrize("year", [2007, 2024, 2025])
def test_live_head(year):
    remote = HttpFileClient(timeout_seconds=60).head(year_url(year))
    assert remote.size and remote.size > 20_000_000


def test_live_2007_escolas(tmp_path):
    payload = InepCensoEscolarDataSource(output_path=str(tmp_path)).download(
        output_dir=str(tmp_path), output_format="csv", start_year=2007
    )
    assert payload["failed_count"] == 0
    frame = pl.read_csv(payload["exported_files"][0], infer_schema=False, n_rows=5)
    assert frame.columns[0] == "NU_ANO_CENSO"
    assert {"CO_ENTIDADE", "IN_AGUA_REDE_PUBLICA", "IN_ESGOTO_REDE_PUBLICA"} <= set(frame.columns)
