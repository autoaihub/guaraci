"""Smoke opcional do layout das séries novas da PNAD Contínua contra ftp.ibge.gov.br.

Desligado por padrão; ``GUARACI_IBGE_MICRODADOS_SMOKE=1`` liga. Baixa só o
programa de leitura (``.txt``), um ano por série, nunca os zips de dados.
"""

from __future__ import annotations

import os

import pytest

from guaraci.ibge.fixed_width import parse_sas_input
from guaraci.ibge.microdados import PESQUISAS, IbgeFtpClient

SMOKE = os.environ.get("GUARACI_IBGE_MICRODADOS_SMOKE") == "1"
pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        not SMOKE,
        reason="Set GUARACI_IBGE_MICRODADOS_SMOKE=1 to enable the live IBGE microdata smoke test",
    ),
]


@pytest.mark.parametrize(
    "key,ano",
    [
        ("ibge_pnadc_visita5", 2024),
        ("ibge_pnadc_trimestre1", 2023),
        ("ibge_pnadc_trimestre2", 2025),
        ("ibge_pnadc_trimestre3", 2025),
        ("ibge_pnadc_trimestre4", 2025),
    ],
)
def test_pnadc_new_series_input_matches_lrecl(tmp_path, key, ano):
    edicao = PESQUISAS[key].edicoes[ano]
    alias, _ = edicao.tabelas[0].layout
    target = tmp_path / f"{key}_{ano}.txt"
    IbgeFtpClient().download(edicao.arquivos[alias], target)
    (block,) = parse_sas_input(target.read_bytes().decode("cp1252"))
    assert len(block.columns) > 300
    assert block.columns[0].name == "Ano"
    assert block.lrecl >= block.record_length  # o IBGE reserva folga no LRECL
