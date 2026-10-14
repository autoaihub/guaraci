"""Censo 2022 no SIDRA (guaraci/ibge/censo.py) e fatiamento do teto de 50 mil valores."""
from __future__ import annotations

import json
import re

import pytest

from guaraci.ibge import censo
from guaraci.ibge.sidra import IbgePopulacaoIdadeSexoDataSource, SidraAggregateSource as S
from guaraci.services.downloads import DownloadService


def _valores(localidade: str, classificacao: str, n_variaveis: int = 1) -> int:
    """Valores que a SIDRA contaria no pedido (municipios x categorias x variaveis)."""
    if localidade == "N6[all]":
        municipios = S._MUNICIPIOS
    else:
        uf = int(re.search(r"N3\[(\d+)\]", localidade).group(1))
        municipios = S._MUNICIPIOS_POR_UF[uf]
    total = municipios * n_variaveis
    for categorias in re.findall(r"\[([^\]]*)\]", classificacao):
        total *= len(categorias.split(","))
    return total


def _combinacoes(classificacao: str) -> set:
    """Conjunto de tuplas (categoria de cada classificacao) que o pedido cobre."""
    listas = [c.split(",") for c in re.findall(r"\[([^\]]*)\]", classificacao)]
    combos = [()]
    for lista in listas:
        combos = [c + (cat,) for c in combos for cat in lista]
    return set(combos)


def test_limite_da_api_e_50_mil_valores():
    assert S._SIDRA_MAX_VALUES == 50_000


def test_mg_na_tabela_9606_e_fatiada_por_categoria_e_cobre_tudo():
    espec = censo.IbgeCensoCorRacaIdadeSexoDataSource.ESPEC
    classif = censo._classificacao(espec, "completo")
    pares = censo.IbgeCensoCorRacaIdadeSexoDataSource._requests("N6", classif, n_variaveis=1)

    mg = [(loc, cl) for loc, cl in pares if loc == "N6[N3[31]]"]
    # 853 municipios x 210 combinacoes = 179.130 valores: nao cabe em um pedido.
    assert _valores("N6[N3[31]]", classif) == 179_130
    assert len(mg) > 1
    assert all(_valores(loc, cl) <= 50_000 for loc, cl in pares)

    # As fatias de MG juntas dao exatamente as 210 combinacoes, sem repetir.
    cobertas = [_combinacoes(cl) for _, cl in mg]
    assert sum(len(c) for c in cobertas) == 210
    assert set().union(*cobertas) == _combinacoes(classif)

    # Todas as 27 UFs aparecem.
    assert {loc for loc, _ in pares} == {f"N6[N3[{uf}]]" for uf in S._UF_CODES}


def test_uf_que_cabe_num_pedido_nao_e_fatiada():
    espec = censo.IbgeCensoCorRacaIdadeSexoDataSource.ESPEC
    classif = censo._classificacao(espec, "completo")
    pares = censo.IbgeCensoCorRacaIdadeSexoDataSource._requests("N6", classif, n_variaveis=1)
    ro = [cl for loc, cl in pares if loc == "N6[N3[11]]"]
    assert ro == [classif]


def test_pedido_entre_50_e_100_mil_valores_agora_e_dividido_por_uf():
    # 5.570 municipios x 12 = 66.840: passava no teto antigo (100 mil) e a API recusa.
    classif = "2[4,5]|287[1,2,3,4,5,6]"
    assert S._localities("N6", classif) != ["N6[all]"]
    assert len(S._localities("N6", classif)) == 27


def test_fontes_existentes_mantem_o_mesmo_pedido():
    # 9514 quinquenal por municipio: 5.570 x 42 estoura e vai por UF; cada UF
    # cabe (MG: 853 x 42 = 35.826), entao a classificacao segue intacta.
    classif = "2[4,5]|287[" + ",".join(str(i) for i in range(21)) + "]"
    pares = IbgePopulacaoIdadeSexoDataSource._requests("N6", classif)
    assert len(pares) == 27
    assert {cl for _, cl in pares} == {classif}
    assert S._requests("N3", classif) == [("N3[all]", classif)]
    assert S._requests("N6", None) == [("N6[all]", None)]


def test_variaveis_juntas_contam_no_teto():
    # 5.570 x 10 categorias = 55.700 > 50 mil com 1 variavel; ja com 1 variavel vai por UF.
    # 5.570 x 5 = 27.850 cabe com 1 variavel, mas com 2 (55.700) nao.
    classif = "2[1,2,3,4,5]"
    assert S._localities("N6", classif, n_variaveis=1) == ["N6[all]"]
    assert len(S._localities("N6", classif, n_variaveis=2)) == 27


class _Cliente:
    base_url = "https://fake.ibge"

    def __init__(self):
        self.calls = []

    def aggregate(self, *, table, variable, period, localities, classificacao=None):
        self.calls.append(
            {"table": table, "variable": variable, "period": period,
             "localities": localities, "classificacao": classificacao}
        )
        nomes = {"86": "Cor ou raça", "2": "Sexo", "287": "Idade", "58": "Grupo de idade",
                 "839": "Existência de deficiência"}
        ids = re.findall(r"(\d+)\[([^\]]*)\]", classificacao or "")
        classificacoes = [
            {"nome": nomes.get(cid, f"C{cid}"), "categoria": {cats.split(",")[0]: f"cat{cats.split(',')[0]}"}}
            for cid, cats in ids
        ]
        return [{
            "id": variable.split("|")[0],
            "unidade": "Pessoas",
            "resultados": [{
                "classificacoes": classificacoes,
                "series": [{"localidade": {"id": "3106200", "nome": "Belo Horizonte"},
                            "serie": {period: "10"}}],
            }],
        }]


def test_fonte_municipal_pede_por_uf_e_fatia_e_respeita_o_teto(tmp_path):
    cliente = _Cliente()
    ds = censo.IbgeCensoCorRacaIdadeSexoDataSource(output_path=str(tmp_path), client=cliente)
    out = ds.download(start_year=2022, end_year=2022, level="municipio", output_format="csv")

    assert out["failed_count"] == 0
    assert len(cliente.calls) > 27  # MG, SP, RS, BA... foram fatiadas alem da UF
    for chamada in cliente.calls:
        assert _valores(chamada["localities"], chamada["classificacao"]) <= 50_000
    assert {c["table"] for c in cliente.calls} == {"9606"}
    assert len(out["exported_files"]) == 1


def test_periodos_fora_da_tabela_sao_ignorados_nos_anos_do_meio(tmp_path):
    cliente = _Cliente()
    ds = censo.IbgeCensoCorRacaIdadeSexoDataSource(output_path=str(tmp_path), client=cliente)
    ds.download(start_year=2010, end_year=2022, level="uf", detalhe="total")
    assert sorted({c["period"] for c in cliente.calls}) == ["2010", "2022"]


def test_detalhe_total_so_pede_a_categoria_total(tmp_path):
    cliente = _Cliente()
    ds = censo.IbgeCensoAdensamentoDataSource(output_path=str(tmp_path), client=cliente)
    ds.download(start_year=2022, end_year=2022, level="brasil", detalhe="total")
    assert cliente.calls[0]["classificacao"] == "1975[73086]|63[95826]|125[2932]"
    assert cliente.calls[0]["variable"] == "381"


def test_rejeita_ano_e_detalhe_invalidos(tmp_path):
    ds = censo.IbgeCensoAlfabetizacaoDataSource(output_path=str(tmp_path), client=_Cliente())
    with pytest.raises(ValueError):
        ds.download(start_year=2010, end_year=2010)
    with pytest.raises(ValueError):
        ds.download(detalhe="alien")


def test_deficiencia_grava_dois_arquivos_e_manifesto_completo(tmp_path):
    cliente = _Cliente()
    ds = censo.IbgeCensoDeficienciaDataSource(output_path=str(tmp_path), client=cliente)
    out = ds.download(start_year=2022, end_year=2022, level="uf", output_format="csv")

    assert {c["table"] for c in cliente.calls} == {"10125", "10132"}
    assert {c["variable"] for c in cliente.calls} == {"11852|12785", "11852"}
    nomes = sorted(p.replace("\\", "/").rsplit("/", 1)[-1] for p in out["exported_files"])
    assert nomes == [
        "ibge_censo_deficiencia_cor_raca_N3_2022_2022.csv",
        "ibge_censo_deficiencia_sexo_idade_N3_2022_2022.csv",
    ]
    manifesto = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifesto["exported_files"]) == 2


def test_as_sete_chaves_estao_registradas_com_detalhe():
    chaves = [
        "ibge_censo_cor_raca_idade_sexo", "ibge_censo_alfabetizacao", "ibge_censo_indigena",
        "ibge_censo_quilombola", "ibge_censo_adensamento", "ibge_censo_paredes",
        "ibge_censo_deficiencia",
    ]
    for chave in chaves:
        nomes = {p["name"] for p in DownloadService().get_source_schema(chave)["params"]}
        assert {"start_year", "end_year", "level", "detalhe"} <= nomes, chave


def test_deficiencia_manifesto_soma_as_duas_passadas(tmp_path):
    ds = censo.IbgeCensoDeficienciaDataSource(output_path=str(tmp_path), client=_Cliente())
    out = ds.download(start_year=2022, end_year=2022, level="uf", output_format="csv")

    # Cada passada devolve uma linha; o manifesto final guarda as duas.
    assert out["documents_found"] == 2
    manifesto = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifesto["documents_found"] == 2
    assert manifesto["stats"]["documents_found"] == 2
    assert manifesto["filters"]["table"] == "10125+10132"


def test_intervalo_entre_censos_e_rejeitado_com_mensagem_clara(tmp_path):
    ds = censo.IbgeCensoCorRacaIdadeSexoDataSource(output_path=str(tmp_path), client=_Cliente())
    with pytest.raises(ValueError) as exc:
        ds.download(start_year=2011, end_year=2021, level="uf")
    msg = str(exc.value)
    assert "nenhum período publicado entre 2011 e 2021" in msg
    assert "2010" in msg and "2022" in msg
