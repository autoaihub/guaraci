"""Tests for the IBGE saneamento domiciliar connectors (offline).

Same fake-client pattern as ``tests/test_ibge_registro_civil_territorio.py``:
the SIDRA HTTP layer is faked, so classification building, the census-year
guard, the municipal x detalhe guardrail (or its confirmed-safe absence for
lixo), export, service registration and the orchestrator profile are all
exercised without a network. Live checks live in ``test_ibge_smoke.py``
(opt-in).
"""
from __future__ import annotations

import pytest

from guaraci.ibge import (
    IbgeSaneamentoAguaDataSource,
    IbgeSaneamentoEsgotoDataSource,
    IbgeSaneamentoLixoDataSource,
)
from guaraci.orchestrator.cadence import profile_for
from guaraci.orchestrator.model import Kind
from guaraci.services.downloads import DownloadService


def _payload(period, variable_id, unidade, *rows, classificacoes=None):
    series = [
        {"localidade": {"id": loc_id, "nome": nome}, "serie": {period: value}}
        for (loc_id, nome, value) in rows
    ]
    return [
        {
            "id": variable_id,
            "unidade": unidade,
            "resultados": [{"classificacoes": classificacoes or [], "series": series}],
        }
    ]


class FakeClient:
    base_url = "https://fake.ibge"

    def __init__(self, by_period=None, raise_for=None):
        self._by_period = by_period or {}
        self._raise_for = set(raise_for or ())
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
        if period in self._raise_for:
            raise Exception(f"no data for {period}")
        return self._by_period.get(
            period, _payload(period, "381", "Unidades", ("3550308", "São Paulo - SP", "0"))
        )


# --------------------------------------------------------------------------- #
# ibge_saneamento_agua
# --------------------------------------------------------------------------- #
def test_saneamento_agua_registered_with_detalhe_param():
    schema = DownloadService().get_source_schema("ibge_saneamento_agua")
    assert schema["mode"] == "ibge api"
    names = {p["name"] for p in schema["params"]}
    assert {"start_year", "end_year", "level", "detalhe"} <= names


def test_saneamento_agua_default_classificacao_is_total(tmp_path):
    client = FakeClient(
        by_period={"2022": _payload("2022", "381", "Unidades", ("3550308", "SP", "100"))}
    )
    ds = IbgeSaneamentoAguaDataSource(output_path=str(tmp_path), client=client)
    payload = ds.download(level="municipio")
    assert payload["documents_found"] == 1
    assert client.calls[0]["classificacao"] == "1821[72129]"
    assert client.calls[0]["localities"] == "N6[all]"
    assert client.calls[0]["period"] == "2022"


def test_saneamento_agua_detalhe_all_at_municipal_rejected(tmp_path):
    ds = IbgeSaneamentoAguaDataSource(output_path=str(tmp_path), client=FakeClient())
    with pytest.raises(ValueError, match="municipio"):
        ds.download(level="municipio", detalhe="all")


def test_saneamento_agua_detalhe_all_at_uf_allowed(tmp_path):
    client = FakeClient(by_period={"2022": _payload("2022", "381", "Unidades", ("35", "SP", "10"))})
    ds = IbgeSaneamentoAguaDataSource(output_path=str(tmp_path), client=client)
    ds.download(level="uf", detalhe="all")
    assert client.calls[0]["classificacao"] == "1821[all]"


def test_saneamento_agua_rejects_non_census_year(tmp_path):
    ds = IbgeSaneamentoAguaDataSource(output_path=str(tmp_path), client=FakeClient())
    with pytest.raises(ValueError, match="2022"):
        ds.download(start_year=2021, end_year=2021)


def test_saneamento_agua_rejects_bad_detalhe(tmp_path):
    ds = IbgeSaneamentoAguaDataSource(output_path=str(tmp_path), client=FakeClient())
    with pytest.raises(ValueError):
        ds.download(detalhe="parcial")


def test_saneamento_agua_profile_floor_2022():
    profile = profile_for("ibge_saneamento_agua", "ibge api")
    assert profile.kind is Kind.API_WINDOW
    assert profile.min_year == 2022


# --------------------------------------------------------------------------- #
# ibge_saneamento_esgoto
# --------------------------------------------------------------------------- #
def test_saneamento_esgoto_default_classificacao_is_total(tmp_path):
    client = FakeClient(
        by_period={"2022": _payload("2022", "381", "Unidades", ("3550308", "SP", "100"))}
    )
    ds = IbgeSaneamentoEsgotoDataSource(output_path=str(tmp_path), client=client)
    ds.download(level="municipio")
    assert client.calls[0]["classificacao"] == "11558[46292]"


def test_saneamento_esgoto_detalhe_all_at_municipal_rejected(tmp_path):
    ds = IbgeSaneamentoEsgotoDataSource(output_path=str(tmp_path), client=FakeClient())
    with pytest.raises(ValueError, match="municipio"):
        ds.download(level="municipio", detalhe="all")


def test_saneamento_esgoto_profile_floor_2022():
    assert profile_for("ibge_saneamento_esgoto", "ibge api").min_year == 2022


# --------------------------------------------------------------------------- #
# ibge_saneamento_lixo
# --------------------------------------------------------------------------- #
def test_saneamento_lixo_default_classificacao_is_total(tmp_path):
    client = FakeClient(
        by_period={"2022": _payload("2022", "381", "Unidades", ("3550308", "SP", "100"))}
    )
    ds = IbgeSaneamentoLixoDataSource(output_path=str(tmp_path), client=client)
    ds.download(level="municipio")
    assert client.calls[0]["classificacao"] == "67[10972]"


def test_saneamento_lixo_detalhe_all_at_municipal_allowed(tmp_path):
    """Confirmed live 2026-08-25: lixo (8 categories) does NOT 500 at
    level=municipio x detalhe=all, unlike agua/esgoto, so no guard here."""
    client = FakeClient(by_period={"2022": _payload("2022", "381", "Unidades", ("3550308", "SP", "10"))})
    ds = IbgeSaneamentoLixoDataSource(output_path=str(tmp_path), client=client)
    ds.download(level="municipio", detalhe="all")
    assert client.calls[0]["classificacao"] == "67[all]"
    assert client.calls[0]["localities"] == "N6[all]"


def test_saneamento_lixo_profile_floor_2022():
    assert profile_for("ibge_saneamento_lixo", "ibge api").min_year == 2022
