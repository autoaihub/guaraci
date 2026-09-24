"""Defeitos achados pela varredura de rotas (scripts/verificar_rotas.py).

Em 2026-09-24 a varredura das 124 fontes mostrou três falhas que a suíte não
cobria: o botão "Estimar volume" respondia 500 nas fontes de arquivo do
portal; o formulário das FTP abria num ano que seis sistemas não publicam; e
``fetch run``/``fetch discover`` sem ``--set`` quebravam com TypeError.
"""

from __future__ import annotations

import datetime

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
