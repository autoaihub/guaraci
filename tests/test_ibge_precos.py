"""Testes offline dos índices de preços do IBGE (IPCA, INPC e IPCA-15) pela SIDRA.

A camada HTTP é substituída por um cliente falso: a faixa mensal, a escolha da tabela por
ano, o guarda de ``detalhe`` e a forma da saída são verificados sem rede.
"""
from __future__ import annotations

import csv

import pytest

from guaraci.ibge.precos import (
    IbgeInpcGruposDataSource,
    IbgeIpca15GruposDataSource,
    IbgeIpca15SerieDataSource,
    IbgeIpcaGruposDataSource,
    IbgeIpcaSerieDataSource,
)


def _payload(variavel_id, nome, serie, localidades=(("1", "Brasil"),), classificacoes=None):
    return [
        {
            "id": variavel_id,
            "variavel": nome,
            "unidade": "%",
            "resultados": [
                {
                    "classificacoes": classificacoes or [],
                    "series": [
                        {"localidade": {"id": i, "nome": n}, "serie": serie}
                        for i, n in localidades
                    ],
                }
            ],
        }
    ]


class FakeClient:
    base_url = "https://fake.ibge"

    def __init__(self, serie=None):
        self.serie = serie or {"202401": "0.42", "202402": "..."}
        self.calls = []

    def aggregate(self, *, table, variable, period, localities, classificacao=None):
        self.calls.append(
            {
                "table": table,
                "variable": variable,
                "period": period,
                "localities": localities,
                "classificacao": classificacao,
            }
        )
        return _payload("63", "IPCA - Variação mensal", self.serie)


def _lines(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def test_serie_pede_o_ano_como_faixa_mensal_e_so_brasil(tmp_path):
    client = FakeClient()
    ds = IbgeIpcaSerieDataSource(str(tmp_path), client=client)
    ds.download(start_year=2024, end_year=2024, output_format="csv")
    assert len(client.calls) == 1
    chamada = client.calls[0]
    assert chamada["table"] == "1737"
    assert chamada["period"] == "202401-202412"
    assert chamada["localities"] == "N1[all]"


def test_serie_saida_tem_periodo_ano_mes_e_nulo_para_reticencias(tmp_path):
    ds = IbgeIpcaSerieDataSource(str(tmp_path), client=FakeClient())
    ds.download(start_year=2024, end_year=2024, output_format="csv")
    rows = _lines(next(tmp_path.glob("*.csv")))
    assert [r["periodo"] for r in rows] == ["202401", "202402"]
    assert [(r["ano"], r["mes"]) for r in rows] == [("2024", "1"), ("2024", "2")]
    assert rows[0]["variavel"] == "IPCA - Variação mensal"
    assert rows[0]["valor"] == "0.42"
    assert rows[1]["valor"] == ""


@pytest.mark.parametrize(
    "cls,ano_antes",
    [(IbgeIpcaSerieDataSource, 1978), (IbgeIpca15SerieDataSource, 1999)],
)
def test_serie_recusa_ano_anterior_ao_piso(tmp_path, cls, ano_antes):
    ds = cls(str(tmp_path), client=FakeClient())
    with pytest.raises(ValueError):
        ds.download(start_year=ano_antes, end_year=ano_antes)


@pytest.mark.parametrize(
    "cls,ano,tabela",
    [
        (IbgeIpcaGruposDataSource, 2006, "2938"),
        (IbgeIpcaGruposDataSource, 2011, "2938"),
        (IbgeIpcaGruposDataSource, 2012, "1419"),
        (IbgeIpcaGruposDataSource, 2019, "1419"),
        (IbgeIpcaGruposDataSource, 2020, "7060"),
        (IbgeInpcGruposDataSource, 2012, "1100"),
        (IbgeInpcGruposDataSource, 2025, "7063"),
        (IbgeIpca15GruposDataSource, 2015, "1705"),
        (IbgeIpca15GruposDataSource, 2024, "7062"),
    ],
)
def test_grupos_escolhe_a_tabela_pelo_ano(tmp_path, cls, ano, tabela):
    ds = cls(str(tmp_path), client=FakeClient())
    assert ds._table_for(ano) == tabela


def test_grupos_troca_de_tabela_no_meio_do_intervalo(tmp_path):
    client = FakeClient()
    ds = IbgeIpcaGruposDataSource(str(tmp_path), client=client)
    ds.download(start_year=2019, end_year=2020, output_format="csv")
    assert [c["table"] for c in client.calls] == ["1419", "7060"]
    assert [c["period"] for c in client.calls] == ["201901-201912", "202001-202012"]


def test_grupos_detalhe_vira_classificacao(tmp_path):
    client = FakeClient()
    ds = IbgeIpcaGruposDataSource(str(tmp_path), client=client)
    ds.download(start_year=2024, end_year=2024, detalhe="saude", output_format="csv")
    assert client.calls[0]["classificacao"] == "315[7169,7660,7661,7683,7697]"
    client = FakeClient()
    ds = IbgeIpcaGruposDataSource(str(tmp_path), client=client)
    ds.download(start_year=2024, end_year=2024, detalhe="todos", output_format="csv")
    assert client.calls[0]["classificacao"] == "315[all]"
    assert len(client.calls) == 1


def test_grupos_todos_fora_do_brasil_pede_mes_a_mes(tmp_path):
    client = FakeClient()
    ds = IbgeIpcaGruposDataSource(str(tmp_path), client=client)
    ds.download(
        start_year=2024,
        end_year=2024,
        level="regiao_metropolitana",
        detalhe="todos",
        output_format="csv",
    )
    assert [c["period"] for c in client.calls] == [f"2024{m:02d}" for m in range(1, 13)]
    assert all(c["localities"] == "N7[all]" for c in client.calls)


def test_grupos_recusa_detalhe_e_ano_invalidos(tmp_path):
    ds = IbgeIpcaGruposDataSource(str(tmp_path), client=FakeClient())
    with pytest.raises(ValueError):
        ds.download(start_year=2024, end_year=2024, detalhe="tudo")
    with pytest.raises(ValueError):
        ds.download(start_year=2005, end_year=2005)
    with pytest.raises(ValueError):
        IbgeInpcGruposDataSource(str(tmp_path), client=FakeClient()).download(
            start_year=2011, end_year=2011
        )
