"""Tests for NASA POWER registration in the download service."""

from __future__ import annotations

from pathlib import Path

import pytest

from guaraci.nasa import power as power_mod
from guaraci.services.downloads import DownloadService


class _FakePowerClient:
    base_url = "https://power.larc.nasa.gov"

    def __init__(self, *, base_url: str | None = None, timeout_seconds: int = 120) -> None:
        if base_url:
            self.base_url = base_url

    def temporal_point(self, **kwargs):  # noqa: ANN003
        return {
            "geometry": {"type": "Point", "coordinates": [-46.63, -23.55, 790.19]},
            "properties": {
                "parameter": {"T2M": {"20240101": 23.15, "20240102": 23.99}}
            },
            "header": {"fill_value": -999.0},
            "parameters": {"T2M": {"units": "C"}},
            "messages": [],
        }


def test_nasa_power_is_registered() -> None:
    service = DownloadService()
    sources = {item.source for item in service.list_sources()}
    assert "nasa_power" in sources


def test_nasa_power_schema_shape() -> None:
    service = DownloadService()
    schema = service.get_source_schema("nasa_power")
    assert schema["source"] == "nasa_power"
    assert schema["mode"] == "nasa power api"

    specs = {item["name"]: item for item in schema["params"]}
    assert {
        "output_dir",
        "output_format",
        "latitude",
        "longitude",
        "start_date",
        "end_date",
        "parameters",
        "temporal",
        "community",
        "keep_raw",
        "timeout",
        "api_base_url",
    } <= set(specs)
    assert specs["latitude"]["required"] is True
    assert specs["longitude"]["required"] is True
    assert specs["start_date"]["required"] is True
    assert "T2M" in specs["parameters"]["allowed_values"]
    assert specs["temporal"]["allowed_values"] == ["daily", "monthly"]
    assert specs["community"]["allowed_values"] == ["AG", "RE", "SB"]


def test_validate_rejects_unknown_param() -> None:
    service = DownloadService()
    with pytest.raises(ValueError):
        service.validate_source_params(
            "nasa_power",
            {
                "latitude": "0",
                "longitude": "0",
                "start_date": "2024-01-01",
                "end_date": "2024-01-02",
                "bogus": "x",
            },
        )


def test_validate_requires_latitude() -> None:
    service = DownloadService()
    with pytest.raises(ValueError):
        service.validate_source_params(
            "nasa_power",
            {
                "longitude": "0",
                "start_date": "2024-01-01",
                "end_date": "2024-01-02",
            },
        )


def test_validate_rejects_invalid_parameter_value() -> None:
    service = DownloadService()
    with pytest.raises(ValueError):
        service.validate_source_params(
            "nasa_power",
            {
                "latitude": "0",
                "longitude": "0",
                "start_date": "2024-01-01",
                "end_date": "2024-01-02",
                "parameters": ["NOT_A_REAL_PARAM"],
            },
        )


def test_run_end_to_end_with_monkeypatched_client(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(power_mod, "NasaPowerClient", _FakePowerClient)
    service = DownloadService()
    result = service.run(
        "nasa_power",
        output_dir=str(tmp_path),
        latitude="-23.55",
        longitude="-46.63",
        start_date="2024-01-01",
        end_date="2024-01-02",
        parameters=["T2M"],
        output_format="csv",
    )
    payload = result.to_dict()
    assert payload["source"] == "nasa_power"
    assert payload["status"] == "success"
    assert payload["documents_found"] == 2
    assert payload["downloaded_count"] == 2
    assert len(payload["exported_files"]) == 1


def test_run_normalizes_lowercase_parameters(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _CapturingClient(_FakePowerClient):
        def temporal_point(self, **kwargs):  # noqa: ANN003
            captured.update(kwargs)
            return super().temporal_point(**kwargs)

    monkeypatch.setattr(power_mod, "NasaPowerClient", _CapturingClient)
    service = DownloadService()
    service.run(
        "nasa_power",
        output_dir=str(tmp_path),
        latitude="-23.55",
        longitude="-46.63",
        start_date="2024-01-01",
        end_date="2024-01-02",
        parameters=["t2m"],
        temporal="DAILY",
    )
    assert list(captured["parameters"]) == ["T2M"]
    assert captured["temporal"] == "daily"
