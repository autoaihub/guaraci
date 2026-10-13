"""Smoke opcional dos microdados do IBGE contra ftp.ibge.gov.br.

Desligado por padrão; ``GUARACI_IBGE_MICRODADOS_SMOKE=1`` liga. Baixa só os
zips de documentação (centenas de KB), nunca os de dados: o que se confere é
que o programa SAS publicado continua no lugar e no formato que o parser lê.
"""

from __future__ import annotations

import os
import zipfile

import pytest

from guaraci.ibge.fixed_width import parse_sas_input
from guaraci.ibge.microdados import PESQUISAS, IbgeFtpClient, _find_member

SMOKE = os.environ.get("GUARACI_IBGE_MICRODADOS_SMOKE") == "1"
pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        not SMOKE,
        reason="Set GUARACI_IBGE_MICRODADOS_SMOKE=1 to enable the live IBGE microdata smoke test",
    ),
]


def _layout(tmp_path, key: str, ano: int):
    edicao = PESQUISAS[key].edicoes[ano]
    alias, programa = edicao.tabelas[0].layout
    target = tmp_path / f"{key}_{ano}.zip"
    IbgeFtpClient().download(edicao.arquivos[alias], target)
    with zipfile.ZipFile(target) as archive:
        text = archive.read(_find_member(archive, programa)).decode("cp1252")
    return parse_sas_input(text)


def test_pns_2019_input_has_1088_variables_matching_lrecl(tmp_path):
    (block,) = _layout(tmp_path, "ibge_pns", 2019)
    assert len(block.columns) == 1088
    assert block.lrecl == block.record_length == 1548


def test_pns_2013_input_matches_lrecl(tmp_path):
    (block,) = _layout(tmp_path, "ibge_pns", 2013)
    assert block.lrecl == block.record_length == 1484


def test_pof_reading_program_has_16_blocks_and_550_variables(tmp_path):
    blocks = _layout(tmp_path, "ibge_pof", 2017)
    assert len(blocks) == 16
    assert sum(len(b.columns) for b in blocks) == 550
    infiles = {b.infile.casefold() for b in blocks}
    membros = {t.membro.casefold() for t in PESQUISAS["ibge_pof"].edicoes[2017].tabelas}
    assert infiles == membros


def test_data_zips_still_answer_head():
    client = IbgeFtpClient()
    for pesquisa in PESQUISAS.values():
        for edicao in pesquisa.edicoes.values():
            for path in edicao.arquivos.values():
                assert client.head(path).size, path
