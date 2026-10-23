"""Séries agropecuárias (PAM, PPM, PEVS), Censo Agropecuário 2017 e Censo 2022 novos."""
from __future__ import annotations

import math
import re

import pytest

from guaraci.ibge import agro, censo
from guaraci.ibge.sidra import SidraAggregateSource as S
from guaraci.services.downloads import DownloadService

CHAVES_ANUAIS = [
    "ibge_pam_lavouras",
    "ibge_ppm_rebanhos",
    "ibge_ppm_aquicultura",
    "ibge_ppm_producao_animal",
    "ibge_pevs_extracao_vegetal",
    "ibge_pevs_silvicultura",
]
CHAVES_CENSO = [
    "ibge_censo_agro_2017_agrotoxicos",
    "ibge_censo_agro_2017_estabelecimentos",
    "ibge_censo_agro_2017_produtor",
    "ibge_censo_rendimento",
    "ibge_censo_frequencia_escolar",
    "ibge_censo_fecundidade",
]


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
            {"nome": f"C{cid}", "categoria": {cats.split(",")[0]: "cat"}} for cid, cats in ids
        ]
        return [{
            "id": variable.split("|")[0],
            "unidade": "Toneladas",
            "resultados": [{
                "classificacoes": classificacoes,
                "series": [{"localidade": {"id": "1100015", "nome": "Alta Floresta"},
                            "serie": {period: "10"}}],
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


def test_pam_tem_85_produtos_e_5_variaveis():
    espec = agro.IbgePamLavourasDataSource.ESPEC
    assert len(espec.classificacao.detalhe) == 85
    assert "0" not in espec.classificacao.detalhe
    assert len(set(espec.classificacao.detalhe)) == 85
    assert espec.variaveis.split("|") == ["8331", "216", "214", "112", "215"]


def test_pam_municipal_numero_de_requisicoes_por_ano_e_o_esperado():
    espec = agro.IbgePamLavourasDataSource.ESPEC
    classif = agro._pedido(espec, "completo")
    pares = agro.IbgePamLavourasDataSource._requests("N6", classif, n_variaveis=5)

    esperado = 0
    for uf in S._UF_CODES:
        por_produto = S._MUNICIPIOS_POR_UF[uf] * 5
        passo = max(1, S._SIDRA_MAX_VALUES // por_produto)
        esperado += math.ceil(85 / passo)
    assert len(pares) == esperado
    # RO cabe em 2 pedidos (52 x 5 x 85 = 22.100 cabe em 1); MG e SP vão em várias fatias.
    assert esperado > 27
    assert all(_valores(loc, cl, 5) <= 50_000 for loc, cl in pares)

    # As fatias de cada UF juntas dão os 85 produtos, sem repetir.
    for uf in S._UF_CODES:
        produtos = []
        for loc, cl in pares:
            if loc == f"N6[N3[{uf}]]":
                produtos += re.search(r"\[([^\]]*)\]", cl).group(1).split(",")
        assert sorted(produtos) == sorted(espec.classificacao.detalhe)


def test_pam_baixa_dois_anos_pedindo_so_o_produto(tmp_path):
    cliente = _Cliente()
    ds = agro.IbgePamLavourasDataSource(output_path=str(tmp_path), client=cliente)
    out = ds.download(start_year=2023, end_year=2024, level="uf", output_format="csv")
    assert out["failed_count"] == 0
    assert {c["period"] for c in cliente.calls} == {"2023", "2024"}
    assert {c["table"] for c in cliente.calls} == {"5457"}
    assert cliente.calls[0]["localities"] == "N3[all]"
    assert cliente.calls[0]["classificacao"].startswith("782[40129,40092,")


def test_detalhe_total_pede_so_o_total_e_3939_nao_tem_total(tmp_path):
    cliente = _Cliente()
    agro.IbgePamLavourasDataSource(output_path=str(tmp_path), client=cliente).download(
        start_year=2024, end_year=2024, level="brasil", detalhe="total"
    )
    assert cliente.calls[0]["classificacao"] == "782[0]"

    cliente = _Cliente()
    agro.IbgePpmRebanhosDataSource(output_path=str(tmp_path), client=cliente).download(
        start_year=2024, end_year=2024, level="brasil", detalhe="total"
    )
    assert cliente.calls[0]["classificacao"].startswith("79[2670,2675,")


def test_ano_antes_do_piso_da_tabela_e_rejeitado(tmp_path):
    ds = agro.IbgePpmAquiculturaDataSource(output_path=str(tmp_path), client=_Cliente())
    with pytest.raises(ValueError):
        ds.download(start_year=2012, end_year=2013)
    with pytest.raises(ValueError):
        ds.download(start_year=2013, end_year=2013, detalhe="alien")


def test_censo_agro_so_aceita_2017_e_usa_ano_padrao(tmp_path):
    cliente = _Cliente()
    ds = agro.IbgeCensoAgro2017EstabelecimentosDataSource(output_path=str(tmp_path), client=cliente)
    ds.download(level="uf", detalhe="total")
    assert {c["period"] for c in cliente.calls} == {"2017"}
    assert cliente.calls[0]["classificacao"] == "829[46302]|221[111195]|218[46502]|12564[41145]"
    with pytest.raises(ValueError):
        ds.download(start_year=2022, end_year=2022)


def test_censo_agro_agrotoxicos_municipal_respeita_o_teto(tmp_path):
    cliente = _Cliente()
    ds = agro.IbgeCensoAgro2017AgrotoxicosDataSource(output_path=str(tmp_path), client=cliente)
    ds.download(level="municipio")
    assert cliente.calls
    for c in cliente.calls:
        assert _valores(c["localities"], c["classificacao"], 1) <= 50_000


def test_censo_2022_novos_pedem_as_variaveis_certas(tmp_path):
    esperado = {
        censo.IbgeCensoRendimentoDataSource: ("10281", "13535|13536|13537"),
        censo.IbgeCensoFrequenciaEscolarDataSource: ("10056", "3795"),
        censo.IbgeCensoFecundidadeDataSource: ("10078", "13315|13316|13317|13318"),
    }
    for cls, (tabela, variaveis) in esperado.items():
        cliente = _Cliente()
        cls(output_path=str(tmp_path), client=cliente).download(level="brasil", detalhe="total")
        assert cliente.calls[0]["table"] == tabela
        assert cliente.calls[0]["variable"] == variaveis
        assert cliente.calls[0]["period"] == "2022"
        # Cada classificação pedida traz uma categoria só (a Total).
        for _, cats in re.findall(r"(\d+)\[([^\]]*)\]", cliente.calls[0]["classificacao"]):
            assert "," not in cats


def test_municipal_dos_censos_novos_respeita_o_teto(tmp_path):
    for cls in (
        censo.IbgeCensoRendimentoDataSource,
        censo.IbgeCensoFrequenciaEscolarDataSource,
        censo.IbgeCensoFecundidadeDataSource,
    ):
        classif = censo._classificacao(cls.ESPEC, "completo")
        n_var = len(cls.ESPEC.variaveis.split("|"))
        pares = cls._requests("N6", classif, n_variaveis=n_var)
        assert all(_valores(loc, cl, n_var) <= 50_000 for loc, cl in pares)


@pytest.mark.parametrize("chave", CHAVES_ANUAIS + CHAVES_CENSO)
def test_chave_registrada_com_esquema(chave):
    parametros = {p["name"] for p in DownloadService().get_source_schema(chave)["params"]}
    assert {"start_year", "end_year", "level", "detalhe"} <= parametros


def test_pam_registrada_com_piso_1974_e_nivel_padrao_municipio():
    params = {p["name"]: p for p in DownloadService().get_source_schema("ibge_pam_lavouras")["params"]}
    assert params["start_year"]["minimum"] == 1974
    assert params["level"]["default"] == "municipio"
    aqui = {p["name"]: p for p in DownloadService().get_source_schema("ibge_ppm_aquicultura")["params"]}
    assert aqui["start_year"]["minimum"] == 2013
