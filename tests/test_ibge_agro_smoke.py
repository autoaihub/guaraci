"""Smoke opt-in das séries agropecuárias e dos Censos novos no SIDRA (API real).

Desligado por padrão; ``GUARACI_IBGE_SMOKE=1`` liga. Pede Rondônia (municípios
de N3 11), um ano, em cada tabela, e confere que a API aceita o pedido e que a
contagem de linhas bate com municípios x variáveis x categorias.
"""
from __future__ import annotations

import os

import pytest

from guaraci.ibge import agro, censo
from guaraci.ibge.client import IbgeSidraClient

SMOKE = os.environ.get("GUARACI_IBGE_SMOKE") == "1"
pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(not SMOKE, reason="Set GUARACI_IBGE_SMOKE=1 to enable the live IBGE smoke test"),
]

_NOVOS_CENSO = [
    censo.IbgeCensoRendimentoDataSource,
    censo.IbgeCensoFrequenciaEscolarDataSource,
    censo.IbgeCensoFecundidadeDataSource,
]


def _rondonia(cls, classif, n_var, periodo):
    cliente = IbgeSidraClient(timeout_seconds=180)
    fonte = cls(output_path=None)
    linhas = 0
    pares = [
        (loc, cl)
        for loc, cl in cls._requests("N6", classif, n_variaveis=n_var)
        if loc == "N6[N3[11]]"
    ]
    assert pares
    for loc, cl in pares:
        payload = cliente.aggregate(
            table=cls.ESPEC.tabela,
            variable=cls.ESPEC.variaveis,
            period=periodo,
            localities=loc,
            classificacao=cl,
        )
        linhas += len(fonte._parse(payload, "N6"))
    esperado = 52 * n_var
    for _, categorias in cls._parse_classificacao(classif):
        esperado *= len(categorias)
    return linhas, esperado


@pytest.mark.parametrize("cls", agro.AGRO_ANUAL_SOURCES, ids=lambda c: c.SOURCE_NAME)
def test_live_rondonia_anual(cls):
    classif = agro._pedido(cls.ESPEC, "completo")
    n_var = len(cls.ESPEC.variaveis.split("|"))
    linhas, esperado = _rondonia(cls, classif, n_var, "2023")
    # A PEVS de silvicultura devolve 50 dos 52 municípios de RO (conferido em
    # 2026-10-23); as demais tabelas trazem todos.
    assert 0.9 * esperado <= linhas <= esperado


@pytest.mark.parametrize(
    "cls", list(agro.CENSO_AGRO_SOURCES) + _NOVOS_CENSO, ids=lambda c: c.SOURCE_NAME
)
def test_live_rondonia_censo(cls):
    classif = censo._classificacao(cls.ESPEC, "completo")
    n_var = len(cls.ESPEC.variaveis.split("|"))
    linhas, esperado = _rondonia(cls, classif, n_var, str(cls.ESPEC.periodos[-1]))
    assert linhas == esperado
