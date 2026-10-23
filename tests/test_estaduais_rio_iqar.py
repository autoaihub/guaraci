"""Testes offline do cliente ArcGIS REST e do IQAR diário do Rio."""

from __future__ import annotations

import csv

import pytest

from guaraci.arcgis import ArcgisClient, ArcgisClientError, epoch_ms_to_iso_date
from guaraci.estaduais.rio_iqar import RioIqarDiarioDataSource
from guaraci.services.downloads import DownloadService
from guaraci.services.sources import estaduais as estaduais_sources

LAYER = {
    "name": "IQAR",
    "maxRecordCount": 2,
    "objectIdField": None,
    "fields": [
        {"name": "objectid", "type": "esriFieldTypeOID"},
        {"name": "data", "type": "esriFieldTypeDate"},
        {"name": "estação", "type": "esriFieldTypeString"},
        {"name": "poluente", "type": "esriFieldTypeString"},
        {"name": "iqar", "type": "esriFieldTypeSmallInteger"},
    ],
}

DAY = 1483239600000  # 2017-01-01T03:00:00Z (meia-noite em Brasília)
RECORDS = [
    {"objectid": 1, "data": DAY, "estação": "CA", "poluente": "O3", "iqar": 82},
    {"objectid": 2, "data": DAY, "estação": "AV", "poluente": "MP10", "iqar": None},
    {"objectid": 3, "data": DAY + 86400000, "estação": "SC", "poluente": "O3", "iqar": 86},
    {"objectid": 4, "data": None, "estação": "BG", "poluente": "CO", "iqar": 10},
    {"objectid": 5, "data": DAY, "estação": "IR", "poluente": "SO2", "iqar": 7},
]


class FakeArcgis(ArcgisClient):
    def __init__(self, records=RECORDS, layer=LAYER) -> None:
        super().__init__()
        self.records = records
        self.layer_json = layer
        self.calls = []

    def get_json(self, url, params):
        self.calls.append((url, dict(params)))
        if not url.endswith("/query"):
            return self.layer_json
        if params.get("returnCountOnly"):
            return {"count": len(self.records)}
        offset = int(params["resultOffset"])
        size = int(params["resultRecordCount"])
        page = self.records[offset:offset + size]
        # Sem exceededTransferLimit de propósito: a leitura deve parar na página vazia.
        return {"features": [{"attributes": a} for a in page]}


def test_epoch_ms_to_iso_date():
    assert epoch_ms_to_iso_date(DAY) == "2017-01-01"
    assert epoch_ms_to_iso_date(None) == ""


def test_layer_reads_oid_from_fields_when_object_id_field_is_missing():
    layer = FakeArcgis().layer("https://x/MapServer/1")
    assert layer.oid_field == "objectid"
    assert layer.max_record_count == 2
    assert layer.date_fields() == ["data"]


def test_pagination_uses_result_offset_ordered_by_oid_until_empty_page():
    fake = FakeArcgis()
    layer = fake.layer("https://x/MapServer/1")
    got = list(fake.iter_features("https://x/MapServer/1", layer))
    assert [r["objectid"] for r in got] == [1, 2, 3, 4, 5]
    queries = [p for u, p in fake.calls if u.endswith("/query") and "resultOffset" in p]
    assert [q["resultOffset"] for q in queries] == [0, 2, 4, 5]
    assert all(q["resultRecordCount"] == 2 and q["orderByFields"] == "objectid" for q in queries)


def test_datasource_exports_published_names_with_iso_dates(tmp_path):
    source = RioIqarDiarioDataSource(str(tmp_path), client=FakeArcgis())
    payload = source.download(output_dir=str(tmp_path), layer_url="https://x/MapServer/1")
    rows = list(csv.reader(open(payload["exported_files"][0], encoding="utf-8")))
    assert rows[0] == ["objectid", "data", "estação", "poluente", "iqar"]
    assert rows[1] == ["1", "2017-01-01", "CA", "O3", "82"]
    assert rows[2] == ["2", "2017-01-01", "AV", "MP10", ""]
    assert rows[4] == ["4", "", "BG", "CO", "10"]
    assert payload["rows"] == 5
    assert payload["export_warning"] is None


def test_count_mismatch_is_reported(tmp_path):
    class Short(FakeArcgis):
        def get_json(self, url, params):
            if params.get("returnCountOnly"):
                return {"count": 9}
            return super().get_json(url, params)

    source = RioIqarDiarioDataSource(str(tmp_path), client=Short())
    payload = source.download(output_dir=str(tmp_path))
    assert "declarou 9" in payload["export_warning"]


def test_arcgis_error_with_http_200_raises(monkeypatch):
    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"error": {"code": 400, "message": "Invalid query"}}'

    monkeypatch.setattr("guaraci.arcgis.client.urlopen", lambda *a, **k: Resp())
    with pytest.raises(ArcgisClientError) as info:
        ArcgisClient(max_attempts=1).get_json("https://x/MapServer/1/query", {})
    assert info.value.retryable is False


def test_registered_schema():
    service = DownloadService(sources=estaduais_sources.build_sources())
    names = {p["name"] for p in service.get_source_schema("rio_iqar_diario")["params"]}
    assert {"output_dir", "output_format", "layer_url"} <= names
