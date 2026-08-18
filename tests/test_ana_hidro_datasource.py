"""Tests for the ANA HidroWebService datasource (offline, fake client)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from guaraci.ana.client import AnaHidroClientError
from guaraci.ana.hidro import AnaHidroDataSource


class _FakeAnaClient:
    base_url = "https://www.ana.gov.br/hidrowebservice"

    def __init__(self, records_by_station: dict | None = None, *, fail_on: set | None = None) -> None:
        self.calls: list[dict] = []
        self._records = records_by_station or {}
        self._fail_on = fail_on or set()

    def serie_telemetrica(self, *, station_id, detail, data_busca, tipo_filtro_data, range_intervalo):
        self.calls.append(
            {
                "station_id": station_id,
                "detail": detail,
                "data_busca": data_busca,
                "tipo_filtro_data": tipo_filtro_data,
                "range_intervalo": range_intervalo,
            }
        )
        if station_id in self._fail_on:
            raise AnaHidroClientError("boom", category="http_error", retryable=False)
        return self._records.get(station_id, [])


def _source(tmp_path: Path, client: _FakeAnaClient) -> AnaHidroDataSource:
    return AnaHidroDataSource(output_path=str(tmp_path), client=client)


def test_single_short_window_single_call(tmp_path: Path) -> None:
    client = _FakeAnaClient(
        {
            "12345678": [
                {"Data_Hora_Medicao": "2024-01-05T00:00:00", "Chuva_Adotada": 3.4},
            ]
        }
    )
    ds = _source(tmp_path, client)
    payload = ds.download(
        station_ids=["12345678"],
        start_date="2024-01-01",
        end_date="2024-01-10",
        variable="chuvas",
    )
    assert len(client.calls) == 1
    assert client.calls[0]["station_id"] == "12345678"
    assert client.calls[0]["detail"] == "adotada"
    assert client.calls[0]["range_intervalo"] == "DIAS_30"
    assert payload["documents_found"] == 1

    df = ds.load_dataframe()
    row = df.row(0, named=True)
    assert row["station_id"] == "12345678"
    assert row["variable"] == "chuvas"
    assert row["chuva_adotada"] == 3.4
    assert row["timestamp"] == "2024-01-05T00:00:00"


def test_window_over_30_days_is_chunked(tmp_path: Path) -> None:
    client = _FakeAnaClient({"1": []})
    ds = _source(tmp_path, client)
    ds.download(
        station_ids=["1"],
        start_date="2024-01-01",
        end_date="2024-03-15",  # 75 days -> 3 chunks of <=30 days
        variable="vazoes",
    )
    assert len(client.calls) == 3
    # chunk end dates must be non-decreasing and land on end_date at the end
    assert client.calls[-1]["data_busca"] == "2024-03-15"


def test_multiple_stations_multiply_calls(tmp_path: Path) -> None:
    client = _FakeAnaClient({"1": [], "2": []})
    ds = _source(tmp_path, client)
    ds.download(
        station_ids=["1", "2"],
        start_date="2024-01-01",
        end_date="2024-01-10",
        variable="cotas",
    )
    assert len(client.calls) == 2
    assert {c["station_id"] for c in client.calls} == {"1", "2"}


def test_export_and_manifest_excludes_credentials(tmp_path: Path) -> None:
    client = _FakeAnaClient({"1": [{"Data_Hora_Medicao": "2024-01-01T00:00:00", "Vazao_Adotada": 12.0}]})
    ds = AnaHidroDataSource(
        output_path=str(tmp_path), client=client, identificador="ID", senha="SECRET"
    )
    payload = ds.download(
        station_ids=["1"],
        start_date="2024-01-01",
        end_date="2024-01-01",
        variable="vazoes",
        output_format="csv",
        keep_raw=True,
    )
    assert len(payload["exported_files"]) == 1
    assert Path(str(payload["raw_file"])).exists()
    manifest_text = Path(str(payload["manifest_path"])).read_text(encoding="utf-8")
    assert "SECRET" not in manifest_text
    manifest = json.loads(manifest_text)
    assert manifest["source"] == "ana_hidro"
    assert manifest["request"]["filters"]["variable"] == "vazoes"
    assert manifest["request"]["filters"]["station_ids"] == ["1"]


def test_progress_events(tmp_path: Path) -> None:
    client = _FakeAnaClient({"1": []})
    ds = _source(tmp_path, client)
    events: list[dict] = []
    ds.download(
        station_ids=["1"],
        start_date="2024-01-01",
        end_date="2024-01-05",
        variable="chuvas",
        progress_callback=events.append,
    )
    names = [e["event"] for e in events]
    assert names[0] == "download_start"
    assert names[-1] == "download_complete"
    assert names.count("file_completed") == 1


def test_missing_credentials_raise(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("GUARACI_ANA_ID", raising=False)
    monkeypatch.delenv("GUARACI_ANA_SENHA", raising=False)
    ds = AnaHidroDataSource(output_path=str(tmp_path))  # no client, no injected creds
    with pytest.raises(ValueError) as excinfo:
        ds.download(
            station_ids=["1"], start_date="2024-01-01", end_date="2024-01-01", variable="chuvas"
        )
    assert "GUARACI_ANA_ID" in str(excinfo.value)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"station_ids": []},
        {"station_ids": "12345"},
        {"variable": "bogus"},
        {"detail": "bogus"},
        {"start_date": "2024-13-01"},
        {"output_format": "xml"},
    ],
)
def test_validation_errors(tmp_path: Path, kwargs: dict) -> None:
    base = {
        "station_ids": ["1"],
        "start_date": "2024-01-01",
        "end_date": "2024-01-02",
        "variable": "chuvas",
    }
    base.update(kwargs)
    ds = _source(tmp_path, _FakeAnaClient({"1": []}))
    with pytest.raises(ValueError):
        ds.download(**base)


def test_start_after_end_rejected(tmp_path: Path) -> None:
    ds = _source(tmp_path, _FakeAnaClient({"1": []}))
    with pytest.raises(ValueError):
        ds.download(
            station_ids=["1"],
            start_date="2024-01-10",
            end_date="2024-01-02",
            variable="chuvas",
        )


def test_client_error_propagates_with_context(tmp_path: Path) -> None:
    client = _FakeAnaClient({}, fail_on={"1"})
    ds = _source(tmp_path, client)
    with pytest.raises(AnaHidroClientError) as excinfo:
        ds.download(
            station_ids=["1"], start_date="2024-01-01", end_date="2024-01-01", variable="chuvas"
        )
    assert "station" in str(excinfo.value).lower() or "1" in str(excinfo.value)
