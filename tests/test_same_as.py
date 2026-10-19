"""Mapa de fontes que são outro caminho para a mesma base."""

from __future__ import annotations

from fastapi.testclient import TestClient

from guaraci.api.main import app
from guaraci.services.downloads import DownloadService
from guaraci.services.same_as import SAME_AS, _check, distinct_count, same_as_for


def test_every_pair_points_to_registered_sources_without_chains():
    keys = [d.source for d in DownloadService().list_sources()]
    assert _check(keys) == {}


def test_list_sources_carries_the_canonical_source():
    by_key = {d.source: d for d in DownloadService().list_sources()}
    assert by_key["srag_demas"].same_as == "srag_arquivos"
    assert by_key["srag_arquivos"].same_as is None
    # Desde 2026-10-19 o SINAN pelo FTP traz zika (ZIKA).
    assert by_key["zikavirus"].same_as == "sinan"
    assert by_key["doses_aplicadas_pni"].same_as == "pni_doses_aplicadas_arquivos"


def test_distinct_count_discounts_only_the_alternative_paths():
    keys = [d.source for d in DownloadService().list_sources()]
    assert distinct_count(keys) == len(keys) - len(SAME_AS)
    assert same_as_for("dengue") == "sinan"


def test_api_exposes_same_as():
    rows = {r["source"]: r for r in TestClient(app).get("/sources").json()}
    assert rows["dengue"]["same_as"] == "sinan"
    assert rows["sinan"]["same_as"] is None
