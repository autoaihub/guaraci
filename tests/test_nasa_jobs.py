"""End-to-end job integration tests for the NASA sources.

These exercise the real DownloadJobService + DownloadService + adapter +
datasource path (only the NASA HTTP client is monkeypatched), validating that
the progress events the NASA datasources emit are consumed correctly by the
async job machinery and that jobs complete with a normalized JobResult.
"""

from __future__ import annotations

from pathlib import Path

from guaraci.nasa import firms as firms_mod
from guaraci.nasa import power as power_mod
from guaraci.services.downloads import DownloadService
from guaraci.services.jobs import DownloadJobService


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


class _FakeFirmsClient:
    base_url = "https://firms.modaps.eosdis.nasa.gov"

    def __init__(self, *, base_url: str | None = None, timeout_seconds: int = 120) -> None:
        if base_url:
            self.base_url = base_url

    def fetch_country_csv(self, **kwargs):  # noqa: ANN003
        return (
            "country_id,latitude,longitude,bright_ti4,acq_date,frp,daynight\n"
            "BRA,-10.5,-55.2,330.1,2024-08-01,12.5,D\n"
        )

    def fetch_area_csv(self, **kwargs):  # noqa: ANN003
        return self.fetch_country_csv(**kwargs)


def test_nasa_power_job_completes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(power_mod, "NasaPowerClient", _FakePowerClient)
    service = DownloadJobService(download_service=DownloadService())

    job = service.create_job(
        source="nasa_power",
        params={
            "output_dir": str(tmp_path),
            "latitude": "-23.55",
            "longitude": "-46.63",
            "start_date": "2024-01-01",
            "end_date": "2024-01-02",
            "parameters": ["T2M"],
            "output_format": "csv",
        },
    )
    finished = service.wait_for_job(job.job_id, timeout_seconds=5.0)

    assert finished.status == "completed"
    assert finished.result is not None
    assert finished.result.source == "nasa_power"
    assert finished.result.downloaded_count == 2
    # The single-request progress event should have been applied.
    assert finished.files_completed >= 1


def test_nasa_firms_job_completes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(firms_mod, "NasaFirmsClient", _FakeFirmsClient)
    monkeypatch.setenv("GUARACI_FIRMS_MAP_KEY", "ENVKEY")
    service = DownloadJobService(download_service=DownloadService())

    job = service.create_job(
        source="nasa_firms",
        params={
            "output_dir": str(tmp_path),
            "start_date": "2024-08-01",
            "end_date": "2024-08-02",
            "product": "VIIRS_SNPP_NRT",
            "output_format": "csv",
        },
    )
    finished = service.wait_for_job(job.job_id, timeout_seconds=5.0)

    assert finished.status == "completed"
    assert finished.result is not None
    assert finished.result.source == "nasa_firms"
    assert finished.result.downloaded_count == 1


def test_nasa_firms_job_fails_without_map_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(firms_mod, "NasaFirmsClient", _FakeFirmsClient)
    monkeypatch.delenv("GUARACI_FIRMS_MAP_KEY", raising=False)
    service = DownloadJobService(download_service=DownloadService())

    job = service.create_job(
        source="nasa_firms",
        params={
            "output_dir": str(tmp_path),
            "start_date": "2024-08-01",
            "end_date": "2024-08-02",
        },
    )
    finished = service.wait_for_job(job.job_id, timeout_seconds=5.0)

    # A missing MAP_KEY surfaces as a clean job failure, not a crash.
    assert finished.status == "failed"
