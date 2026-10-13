"""Smoke opt-in das fontes do Censo no SIDRA (API real).

Desligado por padrao; ``GUARACI_IBGE_SMOKE=1`` liga. Pede o recorte completo de
Rondonia (municipios de N3 11) em cada tabela e confere que a API aceita o
pedido e que a contagem de linhas bate com o produto de categorias.
"""
from __future__ import annotations

import os

import pytest

from guaraci.ibge import censo
from guaraci.ibge.client import IbgeSidraClient

SMOKE = os.environ.get("GUARACI_IBGE_SMOKE") == "1"
pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(not SMOKE, reason="Set GUARACI_IBGE_SMOKE=1 to enable the live IBGE smoke test"),
]


@pytest.mark.parametrize("cls", censo.CENSO_SOURCES, ids=lambda c: c.SOURCE_NAME)
def test_live_rondonia_municipal(cls):
    cliente = IbgeSidraClient(timeout_seconds=180)
    especs = [cls.ESPEC] + ([cls.ESPEC_COR_RACA] if hasattr(cls, "ESPEC_COR_RACA") else [])
    for espec in especs:
        classif = censo._classificacao(espec, "completo")
        n_var = len(espec.variaveis.split("|"))
        pares = [
            (loc, cl)
            for loc, cl in cls._requests("N6", classif, n_variaveis=n_var)
            if loc == "N6[N3[11]]"
        ]
        assert pares
        fonte = cls(output_path=None)
        linhas = 0
        for loc, cl in pares:
            payload = cliente.aggregate(
                table=espec.tabela,
                variable=espec.variaveis,
                period=str(espec.periodos[-1]),
                localities=loc,
                classificacao=cl,
            )
            linhas += len(fonte._parse(payload, "N6"))
        esperado = 52 * n_var
        for _, categorias in censo.SidraAggregateSource._parse_classificacao(classif):
            esperado *= len(categorias)
        assert linhas == esperado
