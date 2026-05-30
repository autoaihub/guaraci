"""Tests for NASA FIRMS registration in the download service."""

from __future__ import annotations

from pathlib import Path

import pytest

from guaraci.nasa import firms as firms_mod
from guaraci.services.downloads import DownloadService

_CSV = (
    "country_id,latitude,longitude,bright_ti4,acq_date,frp,daynight\n"
    "BRA,-10.5,-55.2,330.1,2024-08-01,12.5,D\n"
)


class _FakeFirmsClient:
    base_url = "https://firms.modaps.eosdis.nasa.gov"

    def __init__(self, *, base_url: str | None = None, timeout_seconds: int = 120) -> None:
        if base_url:
            self.base_url = base_url

    def fetch_country_csv(self, **kwargs):  # noqa: ANN003
        return _CSV

    def fetch_area_csv(self, **kwargs):  # noqa: ANN003
        return _CSV


def test_nasa_firms_is_registered() -> None:
    service = DownloadService()
    sources = {item.source for item in service.list_sources()}
    assert "nasa_firms" in sources


def test_nasa_firms_schema_excludes_map_key() -> None:
    service = DownloadService()
    schema = service.get_source_schema("nasa_firms")
    assert schema["mode"] == "nasa firms api"
    names = {item["name"] for item in schema["params"]}
    assert {"start_date", "end_date", "product", "country", "area"} <= names
    # The MAP_KEY is a secret read from the environment, never a job parameter.
    assert "map_key" not in names


def test_nasa_firms_validation_rejects_unknown() -> None:
    service = DownloadService()
    with pytest.raises(ValueError):
        service.validate_source_params(
            "nasa_firms",
            {
                "start_date": "2024-08-01",
                "end_date": "2024-08-02",
                "map_key": "leak",
            },
        )


def test_nasa_firms_run_end_to_end(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(firms_mod, "NasaFirmsClient", _FakeFirmsClient)
    monkeypatch.setenv("GUARACI_FIRMS_MAP_KEY", "ENVKEY")
    service = DownloadService()
    result = service.run(
        "nasa_firms",
        output_dir=str(tmp_path),
        start_date="2024-08-01",
        end_date="2024-08-02",
        product="VIIRS_SNPP_NRT",
        output_format="csv",
    )
    payload = result.to_dict()
    assert payload["source"] == "nasa_firms"
    assert payload["status"] == "success"
    assert payload["documents_found"] == 1
    assert len(payload["exported_files"]) == 1


def test_nasa_firms_run_missing_key_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(firms_mod, "NasaFirmsClient", _FakeFirmsClient)
    monkeypatch.delenv("GUARACI_FIRMS_MAP_KEY", raising=False)
    service = DownloadService()
    with pytest.raises(ValueError):
        service.run(
            "nasa_firms",
            output_dir=str(tmp_path),
            start_date="2024-08-01",
            end_date="2024-08-02",
        )
