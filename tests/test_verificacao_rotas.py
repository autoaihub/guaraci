"""Defeitos achados pela varredura de rotas (scripts/verificar_rotas.py).

Em 2026-09-24 a varredura das 124 fontes mostrou três falhas que a suíte não
cobria: o botão "Estimar volume" respondia 500 nas fontes de arquivo do
portal; o formulário das FTP abria num ano que seis sistemas não publicam; e
``fetch run``/``fetch discover`` sem ``--set`` quebravam com TypeError.
"""

from __future__ import annotations

import datetime

import pytest

from fastapi.testclient import TestClient

from guaraci.api import main as api_main
from guaraci.datasus.ftp.specs import SPECS
from guaraci.orchestrator.cadence import profile_for
from guaraci.orchestrator.planner import plan_backfill
from guaraci.services.downloads import DownloadService


def test_portal_discovery_payload_is_normalised_for_the_api(monkeypatch):
    portal_payload = {
        "dataset": "sisagua_populacao_abastecida",
        "slug": "sisagua",
        "documents_found": 2,
        "resources": [{"name": "a.zip", "size_bytes": None}, {"name": "b.zip", "size_bytes": None}],
    }
    monkeypatch.setattr(api_main.download_service, "discover", lambda source, **kw: dict(portal_payload))
    resp = TestClient(api_main.app).post(
        "/sources/sisagua_populacao_abastecida/discovery", json={"params": {}}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "sisagua_populacao_abastecida"
    assert body["documents_found"] == 2 and body["total_size_bytes"] == 0
    assert [item["name"] for item in body["sample"]] == ["a.zip", "b.zip"]


def test_discontinued_ftp_systems_cap_and_default_to_their_last_year():
    service = DownloadService()
    last = {"cih": 2011, "pni": 2019, "sisprenatal": 2014, "siscan": 2015}
    for source, year in last.items():
        params = {p["name"]: p for p in service.get_source_schema(source)["params"]}
        assert params["start_year"]["maximum"] == year, source
        assert params["end_year"]["default"] == year, source
        assert profile_for(source, "datasus ftp").max_year == year


def test_lagging_ftp_systems_default_to_a_published_year():
    service = DownloadService()
    for source in ("sinasc", "resp"):
        params = {p["name"]: p for p in service.get_source_schema(source)["params"]}
        assert params["start_year"]["default"] == SPECS[source].default_year
        assert params["start_year"]["maximum"] == datetime.date.today().year


def test_backfill_of_a_discontinued_system_stops_at_its_last_year():
    seen = []

    def records(kind, source, years, **_):
        seen.extend(years)
        return []

    plan_backfill(profile_for("pni", "datasus ftp"), current_year=2026, records_provider=records)
    assert seen and max(seen) == 2019


def test_required_params_with_defaults_are_filled_before_dispatch(monkeypatch):
    service = DownloadService()
    captured = {}
    selected = service._get_registered_source("sinasc")
    monkeypatch.setattr(selected, "download", lambda **kw: captured.update(kw) or "ok")
    service.run("sinasc")
    assert captured["start_year"] == captured["end_year"] == SPECS["sinasc"].default_year


# --- segunda passada: coleta real nas 124 fontes ---------------------------


def test_point_query_object_is_a_single_row():
    from guaraci.opendatasus.datasource import OpenDataSUSDataSource

    payload = {"codigo_tipo_unidade": 5, "descricao_tipo_unidade": "HOSPITAL GERAL"}
    assert OpenDataSUSDataSource._extract_demas_rows(payload) == [payload]
    assert OpenDataSUSDataSource._extract_demas_rows({"sinasc": []}) == []


def test_catmat_code_loses_the_portal_prefix():
    from guaraci.opendatasus.datasource import OpenDataSUSDataSource

    norm = OpenDataSUSDataSource._normalize_demas_api_params
    assert norm({"codigoCatmat": "BR0267614"}) == {"codigoCatmat": "267614"}
    assert norm({"codigoCatmat": "267614"}) == {"codigoCatmat": "267614"}


def test_lagging_sources_default_to_their_latest_published_year():
    from guaraci.services.publication_years import LATEST_PUBLISHED_YEAR

    service = DownloadService()
    for source, year in LATEST_PUBLISHED_YEAR.items():
        params = {p["name"]: p for p in service.get_source_schema(source)["params"]}
        assert params["start_year"]["default"] == year, source
        assert params["end_year"]["default"] == year, source
        assert params["start_year"]["maximum"] >= datetime.date.today().year, source


def test_empty_origin_files_get_an_honest_warning(tmp_path):
    import polars as pl

    from guaraci.services.downloads import _all_parquets_empty

    vazio = tmp_path / "RESPAC24.parquet"
    pl.DataFrame().write_parquet(vazio)
    cheio = tmp_path / "RESPBA23.parquet"
    pl.DataFrame({"a": [1]}).write_parquet(cheio)
    assert _all_parquets_empty([str(vazio)])
    assert not _all_parquets_empty([str(vazio), str(cheio)])


def test_optional_params_with_defaults_reach_the_adapter(monkeypatch):
    # ibge_casamentos: ano opcional no schema, obrigatório no adapter.
    service = DownloadService()
    captured = {}
    selected = service._get_registered_source("ibge_casamentos")
    monkeypatch.setattr(selected, "download", lambda **kw: captured.update(kw) or "ok")
    service.run("ibge_casamentos")
    assert captured["start_year"] == captured["end_year"] == 2024


def test_double_encoded_text_is_repaired_and_legit_text_kept():
    from guaraci.opendatasus.datasource import repair_double_encoded, repair_double_encoded_rows

    assert repair_double_encoded("ALTO RIO JURUÃ\u0081") == "ALTO RIO JURUÁ"
    assert repair_double_encoded("ALTO RIO SOLIMÃ\u0095ES") == "ALTO RIO SOLIMÕES"
    assert repair_double_encoded("DECRETO NÂº 2.271/97") == "DECRETO Nº 2.271/97"
    for legit in ("SÃO PAULO", "NÃO INFORMADO", "Fundação", "N�o informado"):
        assert repair_double_encoded(legit) == legit
    rows, n = repair_double_encoded_rows([{"dsei": "JURUÃ\u0081", "n": 1}, {"dsei": "SÃO"}])
    assert n == 1 and rows[0]["dsei"] == "JURUÁ" and rows[1]["dsei"] == "SÃO"


def test_uf_reconhecida_por_nome_e_por_campo_de_notificacao():
    from guaraci.opendatasus.datasource import OpenDataSUSDataSource as D

    # ESAVI: a origem ignora `uf` e só traz o estado por extenso.
    esavi = [{"nome_estado": "São Paulo"}, {"nome_estado": "Paraná"}, {"nome_estado": "SAO PAULO"}]
    assert D._rows_have_uf_field(esavi)
    assert [D._extract_record_uf(r) for r in esavi] == ["SP", "PR", "SP"]
    # Síndrome gripal leve: a sigla vem em estado_notificacao_ibge.
    assert D._extract_record_uf({"estado_notificacao_ibge": "ac", "estado": "Acre"}) == "AC"
    assert D._extract_record_uf({"nome_estado": "Atlântida"}) is None


def test_pagina_do_demas_resiste_a_rodadas_de_timeout(monkeypatch):
    from guaraci.opendatasus.client import OpenDataSUSClientError
    from guaraci.opendatasus.datasource import OpenDataSUSDataSource

    pausas = []
    monkeypatch.setattr(OpenDataSUSDataSource, "_sleep", staticmethod(pausas.append))

    class Cliente:
        chamadas = 0

        def demas_get(self, path, params):
            Cliente.chamadas += 1
            if Cliente.chamadas < 3:
                raise OpenDataSUSClientError("timed out", retryable=True)
            return {"dados": [{"a": 1}]}

    ds = OpenDataSUSDataSource.__new__(OpenDataSUSDataSource)
    assert ds._demas_page_with_pauses(Cliente(), "/x", {}) == {"dados": [{"a": 1}]}
    assert pausas == [30.0, 90.0]

    class Recusa:
        def demas_get(self, path, params):
            raise OpenDataSUSClientError("400", retryable=False)

    pausas.clear()
    with pytest.raises(OpenDataSUSClientError):
        ds._demas_page_with_pauses(Recusa(), "/x", {})
    assert pausas == []


def test_sidra_divide_municipios_por_uf_quando_estoura_o_limite():
    from guaraci.ibge.sidra import SidraAggregateSource as S

    assert S._localities("N3", "2[4,5]|287[1,2,3]") == ["N3[all]"]
    assert S._localities("N6", None) == ["N6[all]"]
    assert S._localities("N6", "2[6794]|287[100362]") == ["N6[all]"]
    partes = S._localities("N6", "2[4,5]|287[" + ",".join(str(i) for i in range(21)) + "]")
    assert len(partes) == 27 and partes[0] == "N6[N3[11]]" and "N6[N3[35]]" in partes
