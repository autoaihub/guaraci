"""Fontes SIDRA de 2026-10-20 (offline): óbitos fetais e por residência do
registro civil, e óbitos, autismo e dificuldade funcional do Censo 2022.

Cliente falso como em ``tests/test_ibge_censo.py``; o smoke ao vivo das três
do Censo entra pelo ``test_ibge_censo_smoke.py`` (parametrizado em
``CENSO_SOURCES``) e o das duas do registro civil em
``test_ibge_sidra_obitos_autismo_smoke.py``.
"""
from __future__ import annotations

import re

import pytest

from guaraci.ibge import censo
from guaraci.ibge.registro_civil import (
    IbgeObitosFetaisRcDataSource,
    IbgeObitosResidenciaRcDataSource,
)
from guaraci.ibge.sidra import SidraAggregateSource as S
from guaraci.services.downloads import DownloadService


class _Cliente:
    base_url = "https://fake.ibge"

    def __init__(self):
        self.calls = []

    def aggregate(self, *, table, variable, period, localities, classificacao=None):
        self.calls.append(
            {"table": table, "variable": variable, "period": period,
             "localities": localities, "classificacao": classificacao}
        )
        ids = re.findall(r"(\d+)\[([^\]]*)\]", classificacao or "")
        classificacoes = [
            {"nome": f"C{cid}", "categoria": {cats.split(",")[0]: f"cat{cats.split(',')[0]}"}}
            for cid, cats in ids
        ]
        return [{
            "id": variable.split("|")[0],
            "unidade": "Pessoas",
            "resultados": [{
                "classificacoes": classificacoes,
                "series": [{"localidade": {"id": "3550308", "nome": "São Paulo - SP"},
                            "serie": {period: "7"}}],
            }],
        }]


def _valores(localidade: str, classificacao: str, n_variaveis: int) -> int:
    if localidade == "N6[all]":
        municipios = S._MUNICIPIOS
    else:
        uf = int(re.search(r"N3\[(\d+)\]", localidade).group(1))
        municipios = S._MUNICIPIOS_POR_UF[uf]
    total = municipios * n_variaveis
    for categorias in re.findall(r"\[([^\]]*)\]", classificacao):
        total *= len(categorias.split(","))
    return total


CHAVES_RC = ("ibge_obitos_fetais_rc", "ibge_obitos_residencia_rc")
CHAVES_CENSO = ("ibge_censo_obitos", "ibge_censo_autismo", "ibge_censo_dificuldade_funcional")


@pytest.mark.parametrize("chave", CHAVES_RC)
def test_registro_civil_registrado_com_mes_sexo(chave):
    schema = DownloadService().get_source_schema(chave)
    assert schema["mode"] == "ibge api"
    params = {p["name"]: p for p in schema["params"]}
    assert {"start_year", "end_year", "level", "mes", "sexo"} <= set(params)
    assert params["start_year"]["minimum"] == 2003


@pytest.mark.parametrize("chave", CHAVES_CENSO)
def test_censo_registrado_com_detalhe(chave):
    params = {p["name"]: p for p in DownloadService().get_source_schema(chave)["params"]}
    assert {"start_year", "end_year", "level", "detalhe"} <= set(params)
    assert params["start_year"]["minimum"] == 2022


def test_obitos_fetais_pede_2990_var_225_no_total(tmp_path):
    cliente = _Cliente()
    ds = IbgeObitosFetaisRcDataSource(output_path=str(tmp_path), client=cliente)
    out = ds.download(start_year=2023, end_year=2024, level="municipio", output_format="csv")
    assert out["failed_count"] == 0
    assert [c["period"] for c in cliente.calls] == ["2023", "2024"]
    assert {c["table"] for c in cliente.calls} == {"2990"}
    assert {c["variable"] for c in cliente.calls} == {"225"}
    assert cliente.calls[0]["classificacao"] == "236[0]|2[0]"
    assert cliente.calls[0]["localities"] == "N6[all]"


def test_obitos_residencia_pede_2654_e_quebra_mes_na_uf(tmp_path):
    cliente = _Cliente()
    ds = IbgeObitosResidenciaRcDataSource(output_path=str(tmp_path), client=cliente)
    ds.download(start_year=2024, end_year=2024, level="uf", mes="all", sexo="ambos")
    assert cliente.calls[0]["table"] == "2654"
    assert cliente.calls[0]["variable"] == "343"
    assert cliente.calls[0]["classificacao"] == "244[all]|2[4,5]"
    assert cliente.calls[0]["localities"] == "N3[all]"


@pytest.mark.parametrize("cls", [IbgeObitosFetaisRcDataSource, IbgeObitosResidenciaRcDataSource])
def test_registro_civil_recusa_mes_mensal_por_municipio(cls, tmp_path):
    ds = cls(output_path=str(tmp_path), client=_Cliente())
    with pytest.raises(ValueError, match="mes"):
        ds.download(start_year=2024, end_year=2024, level="municipio", mes="all")


@pytest.mark.parametrize(
    "cls",
    [
        censo.IbgeCensoObitosDataSource,
        censo.IbgeCensoAutismoDataSource,
        censo.IbgeCensoDificuldadeFuncionalDataSource,
    ],
)
def test_censo_municipal_respeita_o_teto_e_cobre_todas_as_ufs(cls, tmp_path):
    cliente = _Cliente()
    ds = cls(output_path=str(tmp_path), client=cliente)
    out = ds.download(start_year=2022, end_year=2022, level="municipio", output_format="csv")
    assert out["failed_count"] == 0
    n_var = len(cls.ESPEC.variaveis.split("|"))
    assert {c["table"] for c in cliente.calls} == {cls.ESPEC.tabela}
    assert {c["localities"] for c in cliente.calls} == {f"N6[N3[{uf}]]" for uf in S._UF_CODES}
    for chamada in cliente.calls:
        assert _valores(chamada["localities"], chamada["classificacao"], n_var) <= 50_000


def test_censo_obitos_fatias_de_sp_cobrem_as_696_combinacoes():
    espec = censo.IbgeCensoObitosDataSource.ESPEC
    classif = censo._classificacao(espec, "completo")
    pares = censo.IbgeCensoObitosDataSource._requests("N6", classif, n_variaveis=1)
    sp = [cl for loc, cl in pares if loc == "N6[N3[35]]"]
    # 645 municipios x 8 periodos x 3 sexos x 29 idades: muito acima de 50 mil.
    assert len(sp) > 1
    combos = 0
    for cl in sp:
        n = 1
        for cats in re.findall(r"\[([^\]]*)\]", cl):
            n *= len(cats.split(","))
        combos += n
    assert combos == 8 * 3 * 29


def test_dificuldade_funcional_mantem_os_cinco_tipos_no_detalhe_total(tmp_path):
    cliente = _Cliente()
    ds = censo.IbgeCensoDificuldadeFuncionalDataSource(output_path=str(tmp_path), client=cliente)
    ds.download(level="brasil", detalhe="total")
    assert cliente.calls[0]["classificacao"] == "1509[73771,73772,73773,73789,73790]|623[56918]"
    assert cliente.calls[0]["variable"] == "11852|11856"


def test_autismo_detalhe_total(tmp_path):
    cliente = _Cliente()
    ds = censo.IbgeCensoAutismoDataSource(output_path=str(tmp_path), client=cliente)
    ds.download(level="uf", detalhe="total")
    assert cliente.calls[0]["classificacao"] == "2[6794]|58[95253]"
    assert cliente.calls[0]["variable"] == "93|13267|13408"


def test_censo_novas_recusam_ano_fora_de_2022(tmp_path):
    ds = censo.IbgeCensoObitosDataSource(output_path=str(tmp_path), client=_Cliente())
    with pytest.raises(ValueError):
        ds.download(start_year=2010, end_year=2010)
