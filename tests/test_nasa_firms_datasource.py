"""Tests for the NASA FIRMS datasource."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from guaraci.nasa.firms import NasaFirmsDataSource

_CSV_HEADER = (
    "country_id,latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,"
    "satellite,confidence,version,bright_ti5,frp,daynight"
)


def _csv(*rows: str) -> str:
    return "\n".join([_CSV_HEADER, *rows]) + "\n"


class _FakeFirmsClient:
    base_url = "https://firms.modaps.eosdis.nasa.gov"

    def __init__(self, text: str | None = None) -> None:
        self.calls: list[dict] = []
        self._text = text if text is not None else _csv(
            "BRA,-10.5,-55.2,330.1,0.4,0.36,2024-08-01,1730,N,n,2.0NRT,295.3,12.5,D"
        )

    def fetch_country_csv(self, **kwargs):  # noqa: ANN003
        self.calls.append({"endpoint": "country", **kwargs})
        return self._text

    def fetch_area_csv(self, **kwargs):  # noqa: ANN003
        self.calls.append({"endpoint": "area", **kwargs})
        return self._text


def _source(tmp_path: Path, client: _FakeFirmsClient) -> NasaFirmsDataSource:
    return NasaFirmsDataSource(
        output_path=str(tmp_path), client=client, map_key="TESTKEY"
    )


def test_download_parses_and_adds_provenance(tmp_path: Path) -> None:
    client = _FakeFirmsClient()
    ds = _source(tmp_path, client)
    payload = ds.download(
        start_date="2024-08-01", end_date="2024-08-03", product="VIIRS_SNPP_NRT"
    )
    assert payload["documents_found"] == 1
    assert payload["region"] == "country:BRA"
    df = ds.load_dataframe()
    assert "firms_product" in df.columns
    assert df["firms_product"].to_list() == ["VIIRS_SNPP_NRT"]
    assert df["frp"].dtype.is_numeric()


def test_window_is_chunked_into_10_day_segments(tmp_path: Path) -> None:
    client = _FakeFirmsClient()
    ds = _source(tmp_path, client)
    ds.download(start_date="2024-08-01", end_date="2024-08-12")
    assert [call["day_range"] for call in client.calls] == [10, 2]
    assert [call["date"] for call in client.calls] == ["2024-08-01", "2024-08-11"]


def test_area_overrides_country(tmp_path: Path) -> None:
    client = _FakeFirmsClient()
    ds = _source(tmp_path, client)
    ds.download(
        start_date="2024-08-01", end_date="2024-08-02", area="-74,-34,-34,6"
    )
    assert client.calls[0]["endpoint"] == "area"
    assert client.calls[0]["area"] == "-74.0,-34.0,-34.0,6.0"


def test_export_and_manifest_excludes_secret(tmp_path: Path) -> None:
    client = _FakeFirmsClient()
    ds = _source(tmp_path, client)
    payload = ds.download(
        start_date="2024-08-01",
        end_date="2024-08-02",
        output_format="csv",
        keep_raw=True,
    )
    assert len(payload["exported_files"]) == 1
    assert Path(str(payload["raw_file"])).exists()
    manifest_text = Path(str(payload["manifest_path"])).read_text(encoding="utf-8")
    assert "TESTKEY" not in manifest_text
    manifest = json.loads(manifest_text)
    assert manifest["source"] == "nasa_firms"
    assert manifest["request"]["filters"]["region"] == "country:BRA"
    assert "map_key" not in manifest_text


def test_missing_map_key_raises(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("GUARACI_FIRMS_MAP_KEY", raising=False)
    ds = NasaFirmsDataSource(output_path=str(tmp_path), client=_FakeFirmsClient())
    with pytest.raises(ValueError) as excinfo:
        ds.download(start_date="2024-08-01", end_date="2024-08-02")
    assert "MAP_KEY" in str(excinfo.value)


def test_map_key_from_environment(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GUARACI_FIRMS_MAP_KEY", "ENVKEY")
    client = _FakeFirmsClient()
    ds = NasaFirmsDataSource(output_path=str(tmp_path), client=client)
    ds.download(start_date="2024-08-01", end_date="2024-08-02")
    assert client.calls[0]["map_key"] == "ENVKEY"


def test_non_csv_response_raises(tmp_path: Path) -> None:
    client = _FakeFirmsClient(text="Invalid MAP_KEY.")
    ds = _source(tmp_path, client)
    with pytest.raises(Exception) as excinfo:
        ds.download(start_date="2024-08-01", end_date="2024-08-02")
    assert "non-CSV" in str(excinfo.value)


def test_empty_results_emit_warning(tmp_path: Path) -> None:
    client = _FakeFirmsClient(text=_CSV_HEADER + "\n")  # header only, no rows
    ds = _source(tmp_path, client)
    payload = ds.download(
        start_date="2024-08-01", end_date="2024-08-02", output_format="csv"
    )
    assert payload["documents_found"] == 0
    assert payload["exported_files"] == []
    assert "no detections" in payload["export_warning"].lower()


def test_progress_events(tmp_path: Path) -> None:
    client = _FakeFirmsClient()
    ds = _source(tmp_path, client)
    events: list[dict] = []
    ds.download(
        start_date="2024-08-01",
        end_date="2024-08-25",  # 25 days -> 3 segments
        progress_callback=events.append,
    )
    names = [event["event"] for event in events]
    assert names[0] == "download_start"
    assert names[-1] == "download_complete"
    assert names.count("file_completed") == 3
    assert events[0]["documents_total"] == 3


@pytest.mark.parametrize(
    "kwargs",
    [
        {"product": "BOGUS_SAT"},
        {"start_date": "2024-13-01"},
        {"country": "BRAZIL"},
        {"area": "1,2,3"},
        {"area": "10,2,5,8"},  # west >= east
        {"output_format": "xml"},
    ],
)
def test_validation_errors(tmp_path: Path, kwargs: dict) -> None:
    base = {"start_date": "2024-08-01", "end_date": "2024-08-02"}
    base.update(kwargs)
    ds = _source(tmp_path, _FakeFirmsClient())
    with pytest.raises(ValueError):
        ds.download(**base)


def test_start_after_end_rejected(tmp_path: Path) -> None:
    ds = _source(tmp_path, _FakeFirmsClient())
    with pytest.raises(ValueError):
        ds.download(start_date="2024-08-10", end_date="2024-08-02")
