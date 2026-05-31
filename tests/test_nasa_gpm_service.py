"""Tests for NASA GPM IMERG registration in the download service."""

from __future__ import annotations

from pathlib import Path

import pytest

from guaraci.nasa import gpm as gpm_mod
from guaraci.services.downloads import DownloadService

_ASCII = (
    "Dataset: g.nc4\n"
    "precipitation.precipitation[precipitation.time=0][precipitation.lon=-46.65], 4.72\n"
    "precipitation.lat, -23.55\n"
)


class _FakeGesDiscClient:
    base_url = "https://gpm1.gesdisc.eosdis.nasa.gov"

    def __init__(self, *, token: str, base_url: str | None = None, timeout_seconds: int = 120) -> None:
        self.token = token
        if base_url:
            self.base_url = base_url

    def fetch_ascii(self, dataset_path: str, constraint: str) -> str:
        return _ASCII


def test_nasa_gpm_is_registered() -> None:
    service = DownloadService()
    sources = {item.source for item in service.list_sources()}
    assert "nasa_gpm" in sources


def test_nasa_gpm_schema_shape() -> None:
    service = DownloadService()
    schema = service.get_source_schema("nasa_gpm")
    assert schema["mode"] == "nasa gpm api"
    specs = {item["name"]: item for item in schema["params"]}
    assert {
        "latitude",
        "longitude",
        "start_date",
        "end_date",
        "variable",
        "product",
    } <= set(specs)
    assert specs["latitude"]["required"] is True
    assert "precipitation" in specs["variable"]["allowed_values"]
    # The Earthdata token must never be a job parameter.
    assert "token" not in specs
    assert "api_key" not in specs


def test_validate_rejects_unknown_param() -> None:
    service = DownloadService()
    with pytest.raises(ValueError):
        service.validate_source_params(
            "nasa_gpm",
            {
                "latitude": "0",
                "longitude": "0",
                "start_date": "2024-01-01",
                "end_date": "2024-01-02",
                "token": "leak",
            },
        )


def test_run_end_to_end_with_monkeypatched_client(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(gpm_mod, "NasaGesDiscClient", _FakeGesDiscClient)
    monkeypatch.setenv("GUARACI_EARTHDATA_TOKEN", "ENVTOKEN")
    service = DownloadService()
    result = service.run(
        "nasa_gpm",
        output_dir=str(tmp_path),
        latitude="-23.55",
        longitude="-46.63",
        start_date="2024-01-01",
        end_date="2024-01-02",
        variable="precipitation",
        output_format="csv",
    )
    payload = result.to_dict()
    assert payload["source"] == "nasa_gpm"
    assert payload["status"] == "success"
    assert payload["documents_found"] == 2
    assert len(payload["exported_files"]) == 1


def test_run_missing_token_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(gpm_mod, "NasaGesDiscClient", _FakeGesDiscClient)
    monkeypatch.delenv("GUARACI_EARTHDATA_TOKEN", raising=False)
    service = DownloadService()
    with pytest.raises(ValueError):
        service.run(
            "nasa_gpm",
            output_dir=str(tmp_path),
            latitude="-23.55",
            longitude="-46.63",
            start_date="2024-01-01",
            end_date="2024-01-02",
        )
