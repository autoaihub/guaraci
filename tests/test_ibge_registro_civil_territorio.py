"""Tests for the Fase C IBGE connectors (offline): registro civil + território.

Same fake-client pattern as ``tests/test_ibge.py`` — the SIDRA HTTP layer is
faked, so parsing, classification building, the municipal/mes guardrail,
export, service registration and the orchestrator profile are all exercised
without a network. Live checks live in ``test_ibge_smoke.py`` (opt-in).
"""
from __future__ import annotations

import pytest

from guaraci.ibge import (
    IbgeAreaTerritorialDataSource,
    IbgeCasamentosDataSource,
    IbgeDivorciosDataSource,
    IbgeNascidosVivosRcDataSource,
    IbgeObitosRcDataSource,
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
            period, _payload(period, "218", "Pessoas", ("3550308", "São Paulo - SP", "0"))
        )


# --------------------------------------------------------------------------- #
# ibge_nascidos_vivos_rc
# --------------------------------------------------------------------------- #
def test_nascidos_vivos_registered_with_mes_sexo_params():
    schema = DownloadService().get_source_schema("ibge_nascidos_vivos_rc")
    assert schema["mode"] == "ibge api"
    names = {p["name"] for p in schema["params"]}
    assert {"start_year", "end_year", "level", "mes", "sexo"} <= names


def test_nascidos_vivos_default_classificacao_is_total(tmp_path):
    client = FakeClient(
        by_period={"2023": _payload("2023", "218", "Pessoas", ("3550308", "SP", "100"))}
    )
    ds = IbgeNascidosVivosRcDataSource(output_path=str(tmp_path), client=client)
    payload = ds.download(start_year=2023, end_year=2023, level="municipio")
    assert payload["documents_found"] == 1
    assert client.calls[0]["classificacao"] == "235[0]|2[0]"
    assert client.calls[0]["localities"] == "N6[all]"


def test_nascidos_vivos_sexo_ambos_token(tmp_path):
    client = FakeClient(by_period={"2023": _payload("2023", "218", "Pessoas", ("35", "SP", "10"))})
    ds = IbgeNascidosVivosRcDataSource(output_path=str(tmp_path), client=client)
    ds.download(start_year=2023, end_year=2023, level="uf", sexo="ambos")
    assert client.calls[0]["classificacao"] == "235[0]|2[4,5]"


def test_nascidos_vivos_mes_all_at_municipal_rejected(tmp_path):
    ds = IbgeNascidosVivosRcDataSource(output_path=str(tmp_path), client=FakeClient())
    with pytest.raises(ValueError, match="mes"):
        ds.download(start_year=2023, end_year=2023, level="municipio", mes="all")


def test_nascidos_vivos_mes_all_at_uf_allowed(tmp_path):
    client = FakeClient(by_period={"2023": _payload("2023", "218", "Pessoas", ("35", "SP", "10"))})
    ds = IbgeNascidosVivosRcDataSource(output_path=str(tmp_path), client=client)
    ds.download(start_year=2023, end_year=2023, level="uf", mes="all")
    assert client.calls[0]["classificacao"] == "235[all]|2[0]"


def test_nascidos_vivos_rejects_bad_options(tmp_path):
    ds = IbgeNascidosVivosRcDataSource(output_path=str(tmp_path), client=FakeClient())
    with pytest.raises(ValueError):
        ds.download(start_year=2023, end_year=2023, mes="quinzenal")
    with pytest.raises(ValueError):
        ds.download(start_year=2023, end_year=2023, sexo="alien")


def test_nascidos_vivos_profile_floor_2003():
    profile = profile_for("ibge_nascidos_vivos_rc", "ibge api")
    assert profile.kind is Kind.API_WINDOW
    assert profile.min_year == 2003


# --------------------------------------------------------------------------- #
# ibge_obitos_rc
# --------------------------------------------------------------------------- #
def test_obitos_registered_with_mes_sexo_params():
    names = {p["name"] for p in DownloadService().get_source_schema("ibge_obitos_rc")["params"]}
    assert {"mes", "sexo", "level"} <= names


def test_obitos_default_classificacao_is_total(tmp_path):
    client = FakeClient(by_period={"2023": _payload("2023", "343", "Pessoas", ("35", "SP", "50"))})
    ds = IbgeObitosRcDataSource(output_path=str(tmp_path), client=client)
    ds.download(start_year=2023, end_year=2023, level="municipio")
    assert client.calls[0]["classificacao"] == "244[0]|2[0]"


def test_obitos_mes_all_at_municipal_rejected(tmp_path):
    ds = IbgeObitosRcDataSource(output_path=str(tmp_path), client=FakeClient())
    with pytest.raises(ValueError, match="mes"):
        ds.download(start_year=2023, end_year=2023, level="municipio", mes="all")


def test_obitos_profile_floor_2003():
    assert profile_for("ibge_obitos_rc", "ibge api").min_year == 2003


# --------------------------------------------------------------------------- #
# ibge_area_territorial
# --------------------------------------------------------------------------- #
def test_area_territorial_registered():
    schema = DownloadService().get_source_schema("ibge_area_territorial")
    assert schema["mode"] == "ibge api"
    names = {p["name"] for p in schema["params"]}
    assert {"start_year", "end_year", "level"} <= names


def test_area_territorial_bundles_three_variables(tmp_path):
    payload = [
        {
            "id": "93",
            "unidade": "Pessoas",
            "resultados": [
                {
                    "classificacoes": [],
                    "series": [{"localidade": {"id": "1", "nome": "Brasil"}, "serie": {"2022": "203080756"}}],
                }
            ],
        },
        {
            "id": "614",
            "unidade": "Habitante por quilômetro quadrado",
            "resultados": [
                {
                    "classificacoes": [],
                    "series": [{"localidade": {"id": "1", "nome": "Brasil"}, "serie": {"2022": "23.86"}}],
                }
            ],
        },
        {
            "id": "6318",
            "unidade": "Quilômetros quadrados",
            "resultados": [
                {
                    "classificacoes": [],
                    "series": [{"localidade": {"id": "1", "nome": "Brasil"}, "serie": {"2022": "8510417.771"}}],
                }
            ],
        },
    ]
    client = FakeClient(by_period={"2022": payload})
    ds = IbgeAreaTerritorialDataSource(output_path=str(tmp_path), client=client)
    result = ds.download(level="brasil")
    assert result["documents_found"] == 3
    assert client.calls[0]["variable"] == "93|614|6318"
    df = ds.load_dataframe()
    area_row = df.filter(df["variavel_id"] == "6318").row(0, named=True)
    assert area_row["valor"] == pytest.approx(8510417.771)


def test_area_territorial_rejects_non_census_year(tmp_path):
    ds = IbgeAreaTerritorialDataSource(output_path=str(tmp_path), client=FakeClient())
    with pytest.raises(ValueError, match="2022"):
        ds.download(start_year=2021, end_year=2021)


def test_area_territorial_profile_floor_2022():
    profile = profile_for("ibge_area_territorial", "ibge api")
    assert profile.min_year == 2022


# --------------------------------------------------------------------------- #
# ibge_casamentos
# --------------------------------------------------------------------------- #
def test_casamentos_registered_with_mes_param():
    schema = DownloadService().get_source_schema("ibge_casamentos")
    assert schema["mode"] == "ibge api"
    names = {p["name"] for p in schema["params"]}
    assert {"start_year", "end_year", "level", "mes"} <= names


def test_casamentos_default_classificacao_is_total(tmp_path):
    client = FakeClient(
        by_period={"2023": _payload("2023", "4993", "Unidades", ("3550308", "SP", "100"))}
    )
    ds = IbgeCasamentosDataSource(output_path=str(tmp_path), client=client)
    payload = ds.download(start_year=2023, end_year=2023, level="municipio")
    assert payload["documents_found"] == 1
    assert client.calls[0]["classificacao"] == "236[0]|664[0]|665[0]|666[0]|667[0]"
    assert client.calls[0]["localities"] == "N6[all]"


def test_casamentos_mes_all_at_municipal_rejected(tmp_path):
    ds = IbgeCasamentosDataSource(output_path=str(tmp_path), client=FakeClient())
    with pytest.raises(ValueError, match="mes"):
        ds.download(start_year=2023, end_year=2023, level="municipio", mes="all")


def test_casamentos_mes_all_at_uf_allowed(tmp_path):
    client = FakeClient(by_period={"2023": _payload("2023", "4993", "Unidades", ("35", "SP", "10"))})
    ds = IbgeCasamentosDataSource(output_path=str(tmp_path), client=client)
    ds.download(start_year=2023, end_year=2023, level="uf", mes="all")
    assert client.calls[0]["classificacao"] == "236[all]|664[0]|665[0]|666[0]|667[0]"


def test_casamentos_rejects_bad_mes(tmp_path):
    ds = IbgeCasamentosDataSource(output_path=str(tmp_path), client=FakeClient())
    with pytest.raises(ValueError):
        ds.download(start_year=2023, end_year=2023, mes="quinzenal")


def test_casamentos_profile_floor_2013():
    profile = profile_for("ibge_casamentos", "ibge api")
    assert profile.kind is Kind.API_WINDOW
    assert profile.min_year == 2013


# --------------------------------------------------------------------------- #
# ibge_divorcios
# --------------------------------------------------------------------------- #
def test_divorcios_registered_with_detalhe_params():
    schema = DownloadService().get_source_schema("ibge_divorcios")
    names = {p["name"] for p in schema["params"]}
    assert {"idade_marido", "idade_mulher", "tempo_decorrido", "level"} <= names


def test_divorcios_default_classificacao_is_total(tmp_path):
    client = FakeClient(by_period={"2023": _payload("2023", "231", "Unidades", ("35", "SP", "50"))})
    ds = IbgeDivorciosDataSource(output_path=str(tmp_path), client=client)
    ds.download(start_year=2023, end_year=2023, level="municipio")
    assert client.calls[0]["classificacao"] == "274[0]|275[0]|276[0]"


def test_divorcios_any_all_at_municipal_rejected(tmp_path):
    ds = IbgeDivorciosDataSource(output_path=str(tmp_path), client=FakeClient())
    with pytest.raises(ValueError, match="municipio"):
        ds.download(start_year=2023, end_year=2023, level="municipio", tempo_decorrido="all")
    with pytest.raises(ValueError, match="municipio"):
        ds.download(start_year=2023, end_year=2023, level="municipio", idade_marido="all")
    with pytest.raises(ValueError, match="municipio"):
        ds.download(start_year=2023, end_year=2023, level="municipio", idade_mulher="all")


def test_divorcios_all_at_uf_allowed(tmp_path):
    client = FakeClient(by_period={"2023": _payload("2023", "231", "Unidades", ("35", "SP", "10"))})
    ds = IbgeDivorciosDataSource(output_path=str(tmp_path), client=client)
    ds.download(start_year=2023, end_year=2023, level="uf", tempo_decorrido="all")
    assert client.calls[0]["classificacao"] == "274[0]|275[0]|276[all]"


def test_divorcios_rejects_bad_options(tmp_path):
    ds = IbgeDivorciosDataSource(output_path=str(tmp_path), client=FakeClient())
    with pytest.raises(ValueError):
        ds.download(start_year=2023, end_year=2023, idade_marido="alien")


def test_divorcios_profile_floor_2014():
    profile = profile_for("ibge_divorcios", "ibge api")
    assert profile.kind is Kind.API_WINDOW
    assert profile.min_year == 2014
