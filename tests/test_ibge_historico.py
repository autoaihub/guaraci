"""Testes offline do módulo de specs ``ibge_historico``: preços, perfil dos municípios e
estados em edições anteriores e microdados das amostras dos Censos de 2010 e 2000."""
from __future__ import annotations

from pathlib import Path

import pytest

from guaraci.ibge import microdados
from guaraci.ibge.fixed_width import load_frozen_layout
from guaraci.ibge.microdados import PESQUISAS, datasource_for_pesquisa
from guaraci.ibge.microdados_censos import (
    IBGE_CENSO2000_AMOSTRA,
    IBGE_CENSO2010_AMOSTRA,
    PESQUISAS_CENSOS,
)
from guaraci.services.sources import ibge_historico

CHAVES = {
    "ibge_ipca_serie",
    "ibge_inpc_serie",
    "ibge_ipca15_serie",
    "ibge_ipca_grupos",
    "ibge_inpc_grupos",
    "ibge_ipca15_grupos",
    "ibge_munic_edicoes",
    "ibge_estadic",
    "ibge_munic_saneamento",
    "ibge_censo2010_amostra",
    "ibge_censo2000_amostra",
}
LAYOUTS = Path(microdados.__file__).parent / "layouts"
TRAVESSOES = (chr(0x2014), chr(0x2013))


def _fontes():
    return {s.descriptor.source: s for s in ibge_historico.build_sources()}


def _nomes(fonte):
    return {p.name for p in fonte.params_schema()}


def test_build_sources_traz_as_onze_chaves_sem_repetir():
    fontes = ibge_historico.build_sources()
    assert {s.descriptor.source for s in fontes} == CHAVES
    assert len(fontes) == len(CHAVES)


def test_chaves_novas_nao_colidem_com_o_registro_de_microdados():
    assert not {p.key for p in PESQUISAS_CENSOS} & set(PESQUISAS)


def test_precos_tem_parametros_esperados():
    fontes = _fontes()
    assert {"start_year", "end_year", "output_format"} <= _nomes(fontes["ibge_ipca_serie"])
    assert "level" not in _nomes(fontes["ibge_ipca_serie"])
    assert {"level", "detalhe"} <= _nomes(fontes["ibge_inpc_grupos"])
    assert fontes["ibge_ipca15_serie"].descriptor.mode == "ibge api"


def test_perfil_usa_modo_ibge_files_e_seletor_indicadores():
    fontes = _fontes()
    for chave in ("ibge_munic_edicoes", "ibge_estadic", "ibge_munic_saneamento"):
        assert fontes[chave].descriptor.mode == "ibge files"
        assert "indicadores" in _nomes(fontes[chave])


def test_censos_exigem_recorte_por_uf():
    fontes = _fontes()
    for chave in ("ibge_censo2010_amostra", "ibge_censo2000_amostra"):
        ufs = next(p for p in fontes[chave].params_schema() if p.name == "ufs")
        assert ufs.required
        assert "AC" in ufs.allowed_values


def test_censo2010_sao_paulo_vem_em_duas_partes():
    valores = IBGE_CENSO2010_AMOSTRA.recorte.valores
    assert "SP1" in valores and "SP2_RM" in valores and "SP" not in valores
    assert len(valores) == 28
    assert len(IBGE_CENSO2000_AMOSTRA.recorte.valores) == 27


@pytest.mark.parametrize(
    "arquivo,variaveis,posicoes",
    [
        ("censo_2010_domicilios.csv", 76, 172),
        ("censo_2010_pessoas.csv", 244, 540),
        ("censo_2010_emigracao.csv", 19, 74),
        ("censo_2010_mortalidade.csv", 19, 66),
    ],
)
def test_layout_congelado_do_censo2010_e_contiguo(arquivo, variaveis, posicoes):
    bloco = load_frozen_layout(LAYOUTS / arquivo, name=arquivo)
    cols = bloco.columns
    assert len(cols) == variaveis
    esperado = 1
    for c in cols:
        assert c.start == esperado
        esperado += c.width
    assert esperado - 1 == posicoes


def test_layouts_citam_origem_e_nao_trazem_travessao():
    arquivos = list(LAYOUTS.glob("censo_2010_*.csv"))
    assert len(arquivos) == 4
    for arquivo in arquivos:
        texto = arquivo.read_text(encoding="utf-8")
        assert texto.lstrip().startswith("#")
        assert not any(t in texto for t in TRAVESSOES)


def test_tabelas_dos_censos_apontam_para_layout_existente():
    for pesquisa in PESQUISAS_CENSOS:
        for edicao in pesquisa.edicoes.values():
            for tabela in edicao.tabelas:
                alias, programa = tabela.layout
                if alias == microdados._FROZEN:
                    assert (LAYOUTS / programa).exists()
                else:
                    assert alias in edicao.arquivos and programa.upper().endswith(".SAS")
                assert "{cod}" in tabela.membro


def test_datasource_for_pesquisa_nao_altera_o_registro(tmp_path):
    cls = datasource_for_pesquisa(IBGE_CENSO2010_AMOSTRA)
    assert cls.DATASET == "ibge_censo2010_amostra"
    assert "ibge_censo2010_amostra" not in PESQUISAS
    assert cls(output_path=str(tmp_path)) is not None
