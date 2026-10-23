"""Smoke ao vivo de Transferegov, Obrasgov e IPEADATA. Opt-in: ``GUARACI_APIS_PUBLICAS_SMOKE=1``."""

from __future__ import annotations

import os

import polars as pl
import pytest

from guaraci.gestao_publica import (
    ObrasgovProjetosDataSource,
    TransferegovFundoAFundoDataSource,
    TransferegovTransferenciasEspeciaisDataSource,
)
from guaraci.ipea import IpeadataSeriesDataSource

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        os.environ.get("GUARACI_APIS_PUBLICAS_SMOKE") != "1",
        reason="Set GUARACI_APIS_PUBLICAS_SMOKE=1 to enable the live public-API smoke tests",
    ),
]


def test_live_transferegov_tabela_pequena(tmp_path):
    source = TransferegovTransferenciasEspeciaisDataSource(output_path=str(tmp_path))
    result = source.download(tabelas=["finalidade_especial"], output_dir=str(tmp_path))
    assert result["failed_count"] == 0 and result["rows"] > 0


def test_live_transferegov_fundo_a_fundo_tabela_sem_chave(tmp_path):
    source = TransferegovFundoAFundoDataSource(output_path=str(tmp_path))
    result = source.download(tabelas=["programa_beneficiario"], output_dir=str(tmp_path))
    assert result["failed_count"] == 0 and result["rows"] > 0


def test_live_obrasgov_duas_paginas(tmp_path):
    source = ObrasgovProjetosDataSource(output_path=str(tmp_path))
    result = source.download(output_dir=str(tmp_path), tamanho_pagina=20, max_paginas=2)
    assert result["pages"] == 2 and result["rows"] > 20
    frame = pl.read_csv(result["exported_files"][0], infer_schema=False)
    assert "idUnico" in frame.columns


def test_live_ipeadata_duas_series(tmp_path):
    source = IpeadataSeriesDataSource(output_path=str(tmp_path))
    result = source.download(series=["AVS_IVS", "AVIOL12_THOMIC"], output_dir=str(tmp_path))
    assert result["failed_count"] == 0 and result["rows"] > 0
