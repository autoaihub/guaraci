"""Tests for the NASA GPM IMERG datasource (OPeNDAP point subsetting)."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from guaraci.nasa.gpm import NasaGpmDataSource


def _ascii(value: str, lat: str = "-23.55", lon: str = "-46.65") -> str:
    return (
        "Dataset: 3B-DAY.MS.MRG.3IMERG.20240101-S000000-E235959.V07B.nc4\n"
        f"precipitation.precipitation[precipitation.time=0][precipitation.lon={lon}], {value}\n"
        "precipitation.time, 0\n"
        f"precipitation.lon, {lon}\n"
        f"precipitation.lat, {lat}\n"
    )


class _FakeGesDiscClient:
    base_url = "https://gpm1.gesdisc.eosdis.nasa.gov"

    def __init__(self, value_by_day: dict | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self._value_by_day = value_by_day or {}

    def fetch_ascii(self, dataset_path: str, constraint: str) -> str:
        self.calls.append((dataset_path, constraint))
        for stamp, val in self._value_by_day.items():
            if stamp in dataset_path:
                return _ascii(val)
        return _ascii("4.72")


def _source(tmp_path: Path, client: _FakeGesDiscClient) -> NasaGpmDataSource:
    return NasaGpmDataSource(output_path=str(tmp_path), client=client)


def test_daily_download_parses_point(tmp_path: Path) -> None:
    client = _FakeGesDiscClient({"20240101": "4.72", "20240102": "0.10"})
    ds = _source(tmp_path, client)
    payload = ds.download(
        latitude="-23.55",
        longitude="-46.63",
        start_date="2024-01-01",
        end_date="2024-01-02",
        variable="precipitation",
    )
    assert payload["documents_found"] == 2
    assert payload["grid_index"] == [1333, 664]
    assert len(client.calls) == 2
    assert client.calls[0][1] == "precipitation[0][1333][664]"
    assert "GPM_3IMERGDF.07" in client.calls[0][0]

    df = ds.load_dataframe().sort("date")
    rows = df.to_dicts()
    assert rows[0]["precipitation"] == 4.72
    assert rows[0]["date"] == "2024-01-01"
    assert rows[1]["precipitation"] == 0.10
    assert df["latitude"].to_list() == [-23.55, -23.55]


def test_fill_value_becomes_null(tmp_path: Path) -> None:
    client = _FakeGesDiscClient({"20240101": "-9999.9"})
    ds = _source(tmp_path, client)
    ds.download(
        latitude="-23.55",
        longitude="-46.63",
        start_date="2024-01-01",
        end_date="2024-01-01",
    )
    assert ds.load_dataframe()["precipitation"].to_list() == [None]


def test_grid_index_formula(tmp_path: Path) -> None:
    # Equator/prime-ish meridian sanity: lon=-179.95 -> 0, lat=-89.95 -> 0
    client = _FakeGesDiscClient()
    ds = _source(tmp_path, client)
    ds.download(
        latitude="-89.95",
        longitude="-179.95",
        start_date="2024-01-01",
        end_date="2024-01-01",
    )
    assert ds.load_dataframe().shape[0] == 1
    assert client.calls[0][1] == "precipitation[0][0][0]"


def test_export_and_manifest_excludes_token(tmp_path: Path) -> None:
    client = _FakeGesDiscClient()
    ds = NasaGpmDataSource(output_path=str(tmp_path), client=client, token="SECRET")
    payload = ds.download(
        latitude="-23.55",
        longitude="-46.63",
        start_date="2024-01-01",
        end_date="2024-01-01",
        output_format="csv",
        keep_raw=True,
    )
    assert len(payload["exported_files"]) == 1
    assert Path(str(payload["raw_file"])).exists()
    manifest_text = Path(str(payload["manifest_path"])).read_text(encoding="utf-8")
    assert "SECRET" not in manifest_text
    manifest = json.loads(manifest_text)
    assert manifest["source"] == "nasa_gpm"
    assert manifest["request"]["filters"]["variable"] == "precipitation"
    assert "token" not in manifest_text.lower()


def test_progress_events(tmp_path: Path) -> None:
    client = _FakeGesDiscClient()
    ds = _source(tmp_path, client)
    events: list[dict] = []
    ds.download(
        latitude="-23.55",
        longitude="-46.63",
        start_date="2024-01-01",
        end_date="2024-01-03",  # 3 days
        progress_callback=events.append,
    )
    names = [e["event"] for e in events]
    assert names[0] == "download_start"
    assert names[-1] == "download_complete"
    assert names.count("file_completed") == 3
    assert events[0]["documents_total"] == 3
    assert events[-1]["downloaded_count"] == 3


def test_missing_token_raises(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("GUARACI_EARTHDATA_TOKEN", raising=False)
    ds = NasaGpmDataSource(output_path=str(tmp_path))  # no client, no token
    with pytest.raises(ValueError) as excinfo:
        ds.download(
            latitude="0", longitude="0", start_date="2024-01-01", end_date="2024-01-01"
        )
    assert "Earthdata" in str(excinfo.value)


def test_window_cap(tmp_path: Path) -> None:
    ds = _source(tmp_path, _FakeGesDiscClient())
    with pytest.raises(ValueError) as excinfo:
        ds.download(
            latitude="0", longitude="0", start_date="2024-01-01", end_date="2026-01-01"
        )
    assert "days" in str(excinfo.value)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"latitude": "999", "longitude": "0"},
        {"latitude": "0", "longitude": "999"},
        {"latitude": "x", "longitude": "0"},
        {"latitude": "0", "longitude": "0", "start_date": "2024-13-01"},
        {"latitude": "0", "longitude": "0", "variable": "bogus"},
        {"latitude": "0", "longitude": "0", "product": "hourly"},
        {"latitude": "0", "longitude": "0", "output_format": "xml"},
    ],
)
def test_validation_errors(tmp_path: Path, kwargs: dict) -> None:
    base = {
        "latitude": "0",
        "longitude": "0",
        "start_date": "2024-01-01",
        "end_date": "2024-01-02",
    }
    base.update(kwargs)
    ds = _source(tmp_path, _FakeGesDiscClient())
    with pytest.raises(ValueError):
        ds.download(**base)


def test_start_after_end_rejected(tmp_path: Path) -> None:
    ds = _source(tmp_path, _FakeGesDiscClient())
    with pytest.raises(ValueError):
        ds.download(
            latitude="0", longitude="0", start_date="2024-01-10", end_date="2024-01-02"
        )
