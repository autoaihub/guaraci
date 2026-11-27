"""Smoke opt-in das tabelas de códigos (rede real); ``GUARACI_REFERENCIAS_SMOKE=1`` liga.

Baixa só o necessário: CNAE classes (cerca de 0,7 MB), o zip do TSE (139 KB) e a
competência mais recente do SIGTAP restrita a uma tabela pequena (zip de 2 MB).
"""

from __future__ import annotations

import os

import polars as pl
import pytest

from guaraci.referencias import CnaeClassesDataSource, SigtapDataSource, TseMunicipiosDataSource

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        os.environ.get("GUARACI_REFERENCIAS_SMOKE") != "1",
        reason="Set GUARACI_REFERENCIAS_SMOKE=1 to enable the live referencias smoke test",
    ),
]


def test_cnae_classes(tmp_path):
    out = CnaeClassesDataSource(str(tmp_path)).download(output_dir=str(tmp_path))
    frame = pl.read_csv(out["exported_files"][0], infer_schema=False)
    assert frame.height > 600
    assert "grupo_divisao_secao_id" in frame.columns


def test_tse_municipios(tmp_path):
    out = TseMunicipiosDataSource(str(tmp_path)).download(output_dir=str(tmp_path))
    frame = pl.read_csv(out["exported_files"][0], infer_schema=False)
    assert frame.height == 5571
    assert "CD_MUNICIPIO_IBGE" in frame.columns


def test_sigtap_ocupacao(tmp_path):
    out = SigtapDataSource(str(tmp_path)).download(output_dir=str(tmp_path), tabelas=["tb_ocupacao"])
    frame = pl.read_csv(out["exported_files"][0], infer_schema=False)
    assert frame.columns == ["CO_OCUPACAO", "NO_OCUPACAO"]
    assert frame.height > 2000
