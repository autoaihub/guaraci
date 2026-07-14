"""Tests for the IBGE population connector (offline).

The SIDRA HTTP layer is faked, so parsing, missing-value handling, level/year
validation, export, service registration and the orchestrator profile are all
exercised without a network. A live check lives in test_ibge_smoke (opt-in).
"""
from __future__ import annotations

import gzip

import pytest

from guaraci.ibge import (
    IbgePibMunicipiosDataSource,
    IbgePopulacaoDataSource,
    IbgePopulacaoIdadeSexoDataSource,
    IbgeSidraClient,
)
from guaraci.ibge.client import IbgeClientError
from guaraci.orchestrator.cadence import profile_for
from guaraci.orchestrator.model import Kind
from guaraci.orchestrator.planner import plan_backfill
from guaraci.services.downloads import DownloadService


def _payload(period, *rows):
    """Build a SIDRA-shaped response for one variable and some localities."""
    series = [
        {"localidade": {"id": loc_id, "nome": nome}, "serie": {period: value}}
        for (loc_id, nome, value) in rows
    ]
    return [
        {
            "id": "9324",
            "variavel": "População residente estimada",
            "unidade": "Pessoas",
            "resultados": [{"classificacoes": [], "series": series}],
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
            {"table": table, "variable": variable, "period": period, "localities": localities, "classificacao": classificacao}
        )
        if period in self._raise_for:
            raise IbgeClientError(f"no data for {period}", category="configuration")
        return self._by_period.get(period, _payload(period, ("3550308", "São Paulo - SP", "0")))


class _FakeResp:
    def __init__(self, data: bytes, encoding: str = ""):
        self._data = data
        self.headers = {"Content-Encoding": encoding}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._data


def _classif_payload(period, *rows):
    """SIDRA response split by Sexo (C2) + Idade (C287)."""
    resultados = [
        {
            "classificacoes": [
                {"id": "2", "nome": "Sexo", "categoria": {"c": sexo}},
                {"id": "287", "nome": "Idade", "categoria": {"c": idade}},
            ],
            "series": [{"localidade": {"id": "35", "nome": "São Paulo"}, "serie": {period: value}}],
        }
        for (sexo, idade, value) in rows
    ]
    return [{"id": "93", "variavel": "População residente", "unidade": "Pessoas", "resultados": resultados}]


class ClassifClient:
    base_url = "https://fake.ibge"

    def __init__(self, payload):
        self._payload = payload
        self.last = None

    def aggregate(self, *, table, variable, period, localities, classificacao=None):
        self.last = {"classificacao": classificacao, "localities": localities, "period": period}
        return self._payload


# --------------------------------------------------------------------------- #
# client
# --------------------------------------------------------------------------- #
def test_client_builds_sidra_url(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        return _FakeResp(b'[{"id":"9324","resultados":[]}]')

    monkeypatch.setattr("guaraci.ibge.client.urlopen", fake_urlopen)
    out = IbgeSidraClient().aggregate(
        table="6579", variable="9324", period="2021", localities="N6[all]"
    )
    assert out == [{"id": "9324", "resultados": []}]
    assert "/api/v3/agregados/6579/periodos/2021/variaveis/9324" in captured["url"]
    assert "localidades=N6" in captured["url"]


def test_client_rejects_non_array(monkeypatch):
    monkeypatch.setattr(
        "guaraci.ibge.client.urlopen", lambda req, timeout=None: _FakeResp(b'{"not":"a list"}')
    )
    with pytest.raises(IbgeClientError):
        IbgeSidraClient().aggregate(table="6579", variable="9324", period="2021", localities="N6[all]")


# --------------------------------------------------------------------------- #
# datasource: parsing + validation
# --------------------------------------------------------------------------- #
def test_download_parses_records_and_missing_values(tmp_path):
    client = FakeClient(
        by_period={
            "2021": _payload(
                "2021",
                ("3550308", "São Paulo - SP", "11451245"),
                ("3304557", "Rio de Janeiro - RJ", "-"),  # missing -> None
            )
        }
    )
    ds = IbgePopulacaoDataSource(output_path=str(tmp_path), client=client)
    payload = ds.download(start_year=2021, end_year=2021, level="municipio")
    assert payload["documents_found"] == 2
    assert payload["level"] == "N6"
    df = ds.load_dataframe()
    assert df.shape == (2, 7)
    assert df["valor"].to_list() == [11451245, None]
    assert client.calls[0]["localities"] == "N6[all]"


def test_download_spans_year_range_and_skips_failing_year(tmp_path):
    client = FakeClient(
        by_period={
            "2019": _payload("2019", ("3550308", "SP", "10")),
            "2021": _payload("2021", ("3550308", "SP", "12")),
        },
        raise_for={"2020"},  # census/no-data year must not abort the range
    )
    ds = IbgePopulacaoDataSource(output_path=str(tmp_path), client=client)
    payload = ds.download(start_year=2019, end_year=2021)
    assert [c["period"] for c in client.calls] == ["2019", "2020", "2021"]
    assert payload["documents_found"] == 2  # 2019 + 2021, 2020 skipped
    assert "2020 skipped" in payload.get("export_warning", "")


def test_level_alias_resolution(tmp_path):
    ds = IbgePopulacaoDataSource(output_path=str(tmp_path), client=FakeClient())
    ds.download(start_year=2021, end_year=2021, level="uf")
    assert ds._resolve_level("brasil") == "N1"
    with pytest.raises(ValueError):
        ds._resolve_level("planeta")


def test_year_validation(tmp_path):
    ds = IbgePopulacaoDataSource(output_path=str(tmp_path), client=FakeClient())
    with pytest.raises(ValueError):
        ds.download(start_year=2022, end_year=2020)
    with pytest.raises(ValueError):
        ds.download(start_year="notayear", end_year=2020)


def test_export_csv(tmp_path):
    client = FakeClient(by_period={"2021": _payload("2021", ("3550308", "SP", "100"))})
    ds = IbgePopulacaoDataSource(output_path=str(tmp_path), client=client)
    payload = ds.download(start_year=2021, end_year=2021, output_format="csv")
    exported = payload["exported_files"]
    assert exported and exported[0].endswith(".csv")
    from pathlib import Path

    assert Path(exported[0]).exists()


# --------------------------------------------------------------------------- #
# service registration + orchestrator profile
# --------------------------------------------------------------------------- #
def test_registered_in_download_service():
    schema = DownloadService().get_source_schema("ibge_populacao")
    assert schema["mode"] == "ibge api"
    names = {p["name"] for p in schema["params"]}
    assert {"start_year", "end_year", "level", "output_format"} <= names


def test_service_validation_accepts_and_rejects():
    service = DownloadService()
    service.validate_source_params("ibge_populacao", {"start_year": 2020, "end_year": 2021})
    with pytest.raises(ValueError):
        service.validate_source_params("ibge_populacao", {"bogus": 1})


def test_orchestrator_profile_and_backfill_years():
    profile = profile_for("ibge_populacao", "ibge api")
    assert profile.kind is Kind.API_WINDOW
    assert profile.min_year == 2001 and profile.auto is True
    units = plan_backfill(profile, current_year=2003)
    assert [u.year for u in units] == [2001, 2002, 2003]


# --------------------------------------------------------------------------- #
# client robustness (gzip + classificacao)
# --------------------------------------------------------------------------- #
def test_client_decompresses_gzip(monkeypatch):
    body = gzip.compress(b'[{"id":"9324","resultados":[]}]')
    monkeypatch.setattr(
        "guaraci.ibge.client.urlopen",
        lambda req, timeout=None: _FakeResp(body, encoding="gzip"),
    )
    out = IbgeSidraClient().aggregate(table="6579", variable="9324", period="2021", localities="N6[all]")
    assert out == [{"id": "9324", "resultados": []}]


def test_client_puts_classificacao_in_url(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        return _FakeResp(b"[]")

    monkeypatch.setattr("guaraci.ibge.client.urlopen", fake_urlopen)
    IbgeSidraClient().aggregate(
        table="9514", variable="93", period="2022", localities="N3[all]",
        classificacao="2[4,5]|287[93070]",
    )
    assert "classificacao=2" in captured["url"] and "287" in captured["url"]


# --------------------------------------------------------------------------- #
# ibge_pib_municipios
# --------------------------------------------------------------------------- #
def test_pib_registered_and_parses(tmp_path):
    schema = DownloadService().get_source_schema("ibge_pib_municipios")
    assert schema["mode"] == "ibge api"
    client = FakeClient(by_period={"2021": _payload("2021", ("3550308", "SP", "836000000"))})
    ds = IbgePibMunicipiosDataSource(output_path=str(tmp_path), client=client)
    ds.download(start_year=2021, end_year=2021)
    assert ds.load_dataframe()["valor"].to_list() == [836000000]


def test_pib_profile_floor_2002():
    assert profile_for("ibge_pib_municipios", "ibge api").min_year == 2002


# --------------------------------------------------------------------------- #
# ibge_populacao_idade_sexo (classifications)
# --------------------------------------------------------------------------- #
def test_idade_sexo_registered_with_classification_params():
    names = {p["name"] for p in DownloadService().get_source_schema("ibge_populacao_idade_sexo")["params"]}
    assert {"sexo", "faixa_etaria", "level"} <= names


def test_idade_sexo_parses_classification_columns(tmp_path):
    payload = _classif_payload("2022", ("Homens", "0 a 4 anos", "1000"), ("Mulheres", "0 a 4 anos", "950"))
    client = ClassifClient(payload)
    ds = IbgePopulacaoIdadeSexoDataSource(output_path=str(tmp_path), client=client)
    ds.download(start_year=2022, end_year=2022, level="uf", sexo="ambos", faixa_etaria="quinquenal")
    df = ds.load_dataframe()
    assert {"sexo", "idade"} <= set(df.columns)
    assert set(df["sexo"].to_list()) == {"Homens", "Mulheres"}
    # ambos -> both sex codes; quinquenal -> the 5-year group ids
    assert client.last["classificacao"].startswith("2[4,5]|287[93070")


def test_idade_sexo_rejects_bad_options(tmp_path):
    ds = IbgePopulacaoIdadeSexoDataSource(output_path=str(tmp_path), client=ClassifClient([]))
    with pytest.raises(ValueError):
        ds.download(start_year=2022, end_year=2022, sexo="alien")
    with pytest.raises(ValueError):
        ds.download(start_year=2022, end_year=2022, faixa_etaria="decadal")


def test_idade_sexo_profile_floor_2022():
    assert profile_for("ibge_populacao_idade_sexo", "ibge api").min_year == 2022
