"""Tests for the NASA POWER datasource."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import polars as pl
import pytest

from guaraci.nasa.power import NasaPowerDataSource


class _FakeDailyClient:
    base_url = "https://power.larc.nasa.gov"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def temporal_point(self, **kwargs):  # noqa: ANN003
        self.calls.append(kwargs)
        return {
            "geometry": {"type": "Point", "coordinates": [-46.63, -23.55, 790.19]},
            "properties": {
                "parameter": {
                    "T2M": {"20240101": 23.15, "20240102": 23.99, "20240103": -999.0},
                    "PRECTOTCORR": {
                        "20240101": 0.06,
                        "20240102": 0.37,
                        "20240103": 4.72,
                    },
                }
            },
            "header": {"fill_value": -999.0, "start": "20240101", "end": "20240103"},
            "parameters": {
                "T2M": {"units": "C", "longname": "Temperature at 2 Meters"},
                "PRECTOTCORR": {"units": "mm/day", "longname": "Precipitation"},
            },
            "messages": [],
        }


class _FakeMonthlyClient:
    base_url = "https://power.larc.nasa.gov"

    def temporal_point(self, **kwargs):  # noqa: ANN003
        self.kwargs = kwargs
        return {
            "geometry": {"type": "Point", "coordinates": [-46.63, -23.55, 790.19]},
            "properties": {
                "parameter": {
                    "T2M": {"202301": 21.67, "202312": 24.66, "202313": 20.38}
                }
            },
            "header": {"fill_value": -999.0},
            "parameters": {"T2M": {"units": "C"}},
            "messages": [],
        }


class _FakeEmptyClient:
    base_url = "https://power.larc.nasa.gov"

    def temporal_point(self, **kwargs):  # noqa: ANN003
        return {
            "geometry": {"type": "Point", "coordinates": [0.0, 0.0, 0.0]},
            "properties": {"parameter": {}},
            "header": {"fill_value": -999.0},
            "parameters": {},
            "messages": ["No data available for the requested configuration."],
        }


def _daily_source(tmp_path: Path) -> NasaPowerDataSource:
    return NasaPowerDataSource(output_path=str(tmp_path), client=_FakeDailyClient())


def test_daily_download_parses_records(tmp_path: Path) -> None:
    ds = _daily_source(tmp_path)
    payload = ds.download(
        latitude="-23.55",
        longitude="-46.63",
        start_date="2024-01-01",
        end_date="2024-01-03",
        parameters=["T2M", "PRECTOTCORR"],
    )

    assert payload["documents_found"] == 3
    assert payload["downloaded_count"] == 3
    assert payload["temporal"] == "daily"
    assert payload["units"]["T2M"] == "C"

    df = ds.load_dataframe()
    assert df.shape == (3, 10)
    assert df.columns[:5] == ["period", "date", "year", "month", "day"]
    # The fill value (-999) must become null.
    third = df.filter(pl.col("period") == "20240103")
    assert third["T2M"].to_list() == [None]
    assert third["PRECTOTCORR"].to_list() == [4.72]
    assert df["latitude"].to_list() == [-23.55, -23.55, -23.55]
    assert df["elevation"].to_list() == [790.19, 790.19, 790.19]


def test_daily_passes_yyyymmdd_window_to_client(tmp_path: Path) -> None:
    client = _FakeDailyClient()
    ds = NasaPowerDataSource(output_path=str(tmp_path), client=client)
    ds.download(
        latitude="1.0",
        longitude="2.0",
        start_date="2024-01-01",
        end_date="2024-01-03",
    )
    assert client.calls[0]["start"] == "20240101"
    assert client.calls[0]["end"] == "20240103"
    assert client.calls[0]["temporal"] == "daily"


def test_default_parameters_used_when_omitted(tmp_path: Path) -> None:
    client = _FakeDailyClient()
    ds = NasaPowerDataSource(output_path=str(tmp_path), client=client)
    ds.download(
        latitude="1.0",
        longitude="2.0",
        start_date="2024-01-01",
        end_date="2024-01-03",
    )
    assert tuple(client.calls[0]["parameters"]) == NasaPowerDataSource.DEFAULT_PARAMETERS


def test_monthly_download_keeps_annual_aggregate(tmp_path: Path) -> None:
    client = _FakeMonthlyClient()
    ds = NasaPowerDataSource(output_path=str(tmp_path), client=client)
    ds.download(
        latitude="-23.55",
        longitude="-46.63",
        start_date="2023-01-01",
        end_date="2023-12-31",
        parameters=["T2M"],
        temporal="monthly",
    )
    # Monthly windows are sent to the API as plain years.
    assert client.kwargs["start"] == "2023"
    assert client.kwargs["end"] == "2023"

    df = ds.load_dataframe().sort("period")
    rows = {r["period"]: r for r in df.to_dicts()}
    assert rows["202301"]["date"] == "2023-01-01"
    assert rows["202301"]["month"] == 1
    # Month 13 is POWER's annual aggregate: preserved with no date.
    assert rows["202313"]["month"] == 13
    assert rows["202313"]["date"] is None
    assert rows["202313"]["T2M"] == 20.38


def test_export_csv_and_parquet_roundtrip(tmp_path: Path) -> None:
    ds = _daily_source(tmp_path)
    payload = ds.download(
        latitude="-23.55",
        longitude="-46.63",
        start_date="2024-01-01",
        end_date="2024-01-03",
        parameters=["T2M"],
        output_format="csv",
    )
    exported = payload["exported_files"]
    assert len(exported) == 1
    csv_path = Path(exported[0])
    assert csv_path.exists() and csv_path.suffix == ".csv"
    reloaded = pl.read_csv(csv_path)
    assert reloaded.shape[0] == 3

    payload2 = ds.download(
        latitude="-23.55",
        longitude="-46.63",
        start_date="2024-01-01",
        end_date="2024-01-03",
        parameters=["T2M"],
        output_format="parquet",
    )
    parquet_path = Path(payload2["exported_files"][0])
    assert pl.read_parquet(parquet_path).shape[0] == 3


def test_export_sqlite(tmp_path: Path) -> None:
    ds = _daily_source(tmp_path)
    payload = ds.download(
        latitude="-23.55",
        longitude="-46.63",
        start_date="2024-01-01",
        end_date="2024-01-03",
        parameters=["T2M"],
        output_format="sqlite",
    )
    sqlite_path = Path(payload["exported_files"][0])
    with sqlite3.connect(sqlite_path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM nasa_power_records"
        ).fetchone()[0]
    assert count == 3


def test_keep_raw_writes_snapshot_and_manifest(tmp_path: Path) -> None:
    ds = _daily_source(tmp_path)
    payload = ds.download(
        latitude="-23.55",
        longitude="-46.63",
        start_date="2024-01-01",
        end_date="2024-01-03",
        parameters=["T2M"],
        keep_raw=True,
    )
    raw_file = Path(str(payload["raw_file"]))
    assert raw_file.exists() and raw_file.parent.name == "raw"

    manifest = json.loads(Path(str(payload["manifest_path"])).read_text(encoding="utf-8"))
    assert manifest["source"] == "nasa_power"
    assert manifest["request"]["filters"]["temporal"] == "daily"
    assert manifest["request"]["filters"]["parameters"] == ["T2M"]


def test_no_artifact_emits_warning(tmp_path: Path) -> None:
    ds = _daily_source(tmp_path)
    payload = ds.download(
        latitude="-23.55",
        longitude="-46.63",
        start_date="2024-01-01",
        end_date="2024-01-03",
        parameters=["T2M"],
    )
    assert "export_warning" in payload
    assert "keep_raw" in payload["export_warning"]


def test_empty_response_surfaces_messages(tmp_path: Path) -> None:
    ds = NasaPowerDataSource(output_path=str(tmp_path), client=_FakeEmptyClient())
    payload = ds.download(
        latitude="0",
        longitude="0",
        start_date="2024-01-01",
        end_date="2024-01-03",
        parameters=["T2M"],
        output_format="csv",
    )
    assert payload["documents_found"] == 0
    assert payload["exported_files"] == []
    assert "No data available" in payload["export_warning"]
    assert ds.load_dataframe().is_empty()


def test_progress_events_match_jobs_contract(tmp_path: Path) -> None:
    ds = _daily_source(tmp_path)
    events: list[dict] = []
    ds.download(
        latitude="-23.55",
        longitude="-46.63",
        start_date="2024-01-01",
        end_date="2024-01-03",
        parameters=["T2M"],
        progress_callback=events.append,
    )
    names = [event["event"] for event in events]
    assert names == ["download_start", "file_completed", "download_complete"]
    assert events[0]["documents_total"] == 1
    assert events[1]["files_completed"] == 1
    assert events[-1]["downloaded_count"] == 3
    assert events[-1]["output_dir"] == str(tmp_path)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"latitude": "999", "longitude": "0"},
        {"latitude": "0", "longitude": "999"},
        {"latitude": "abc", "longitude": "0"},
        {"latitude": "0", "longitude": "0", "start_date": "2024-13-01"},
        {"latitude": "0", "longitude": "0", "temporal": "weekly"},
        {"latitude": "0", "longitude": "0", "community": "ZZ"},
        {"latitude": "0", "longitude": "0", "parameters": ["NOPE"]},
        {"latitude": "0", "longitude": "0", "output_format": "xml"},
    ],
)
def test_validation_errors(tmp_path: Path, kwargs: dict) -> None:
    base = {
        "latitude": "0",
        "longitude": "0",
        "start_date": "2024-01-01",
        "end_date": "2024-01-03",
    }
    base.update(kwargs)
    ds = NasaPowerDataSource(output_path=str(tmp_path), client=_FakeDailyClient())
    with pytest.raises(ValueError):
        ds.download(**base)


def test_start_after_end_rejected(tmp_path: Path) -> None:
    ds = _daily_source(tmp_path)
    with pytest.raises(ValueError):
        ds.download(
            latitude="0",
            longitude="0",
            start_date="2024-01-10",
            end_date="2024-01-02",
        )


def test_load_dataframe_empty_before_download(tmp_path: Path) -> None:
    ds = NasaPowerDataSource(output_path=str(tmp_path), client=_FakeDailyClient())
    assert ds.load_dataframe().is_empty()
