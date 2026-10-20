"""Smoke opt-in dos óbitos fetais (2990) e por residência (2654) na API real.

Desligado por padrao; ``GUARACI_IBGE_SMOKE=1`` liga. Pede 2024, municipios de
Rondonia, no recorte padrao (mes e sexo no Total). As tres fontes novas do
Censo passam pelo ``test_ibge_censo_smoke.py``.
"""
from __future__ import annotations

import os

import pytest

from guaraci.ibge.client import IbgeSidraClient
from guaraci.ibge.registro_civil import (
    IbgeObitosFetaisRcDataSource,
    IbgeObitosResidenciaRcDataSource,
)

SMOKE = os.environ.get("GUARACI_IBGE_SMOKE") == "1"
pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(not SMOKE, reason="Set GUARACI_IBGE_SMOKE=1 to enable the live IBGE smoke test"),
]


@pytest.mark.parametrize(
    "cls,mes_id",
    [(IbgeObitosFetaisRcDataSource, "236"), (IbgeObitosResidenciaRcDataSource, "244")],
)
def test_live_rondonia_2024(cls, mes_id):
    cliente = IbgeSidraClient(timeout_seconds=180)
    payload = cliente.aggregate(
        table=cls.TABLE,
        variable=cls.VARIABLE,
        period="2024",
        localities="N6[N3[11]]",
        classificacao=f"{mes_id}[0]|2[0]",
    )
    linhas = cls(output_path=None)._parse(payload, "N6")
    assert len(linhas) == 52
    assert sum(1 for linha in linhas if linha.get("valor")) > 0
