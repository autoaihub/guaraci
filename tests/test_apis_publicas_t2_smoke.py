"""Smoke ao vivo de SICOR, PNCP e Compras.gov.br. Opt-in: ``GUARACI_APIS_PUBLICAS_SMOKE=1``."""

from __future__ import annotations

import os
import re

import polars as pl
import pytest

from guaraci.bcb import SicorComercializacaoUfDataSource
from guaraci.gestao_publica import ComprasCatmatSaudeDataSource, PncpContratacoesDataSource

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        os.environ.get("GUARACI_APIS_PUBLICAS_SMOKE") != "1",
        reason="Set GUARACI_APIS_PUBLICAS_SMOKE=1 to enable the live public-API smoke tests",
    ),
]


def _cpf_valido(digits: str) -> bool:
    if len(set(digits)) == 1:
        return False
    for size in (9, 10):
        total = sum(int(d) * (size + 1 - i) for i, d in enumerate(digits[:size]))
        if (total * 10 % 11) % 10 != int(digits[size]):
            return False
    return True


def test_live_sicor_comercializacao_um_mes(tmp_path):
    source = SicorComercializacaoUfDataSource(output_path=str(tmp_path))
    result = source.download(start_year=2024, end_year=2024, meses=[3], output_dir=str(tmp_path))
    assert result["rows"] > 0
    frame = pl.read_csv(result["exported_files"][0], infer_schema=False)
    assert {"nomeUF", "AnoEmissao", "VlComerc"} <= set(frame.columns)
    assert set(frame["MesEmissao"].to_list()) == {"03"}


def test_live_pncp_um_dia_uma_modalidade_e_varredura_de_cpf(tmp_path):
    source = PncpContratacoesDataSource(output_path=str(tmp_path))
    result = source.download(
        start_date="2026-09-01", modalidades=[6], max_paginas=2, output_dir=str(tmp_path)
    )
    assert result["rows"] > 50
    frame = pl.read_csv(result["exported_files"][0], infer_schema=False)
    assert {"numeroControlePNCP", "orgaoEntidade_cnpj", "unidadeOrgao_codigoIbge"} <= set(frame.columns)
    found = 0
    for column in frame.columns:
        for value in frame[column].drop_nulls().to_list():
            for match in re.findall(r"(?<!\d)\d{11}(?!\d)", value):
                found += _cpf_valido(match)
    print(f"CPF com digito verificador valido na amostra PNCP ({result['rows']} linhas): {found}")


def test_live_compras_catmat_duas_paginas(tmp_path):
    source = ComprasCatmatSaudeDataSource(output_path=str(tmp_path))
    result = source.download(tamanho_pagina=100, max_paginas=2, output_dir=str(tmp_path))
    assert result["rows"] == 200
    frame = pl.read_csv(result["exported_files"][0], infer_schema=False)
    assert {"codigoItem", "codigoGrupo", "nomeClasse", "descricaoItem"} <= set(frame.columns)
