"""Tests for INMET registration in the download service."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from guaraci.inmet import datasource as datasource_mod
from guaraci.services.downloads import DownloadService

SP_CSV = (
    "REGIAO:;SE\r\n"
    "UF:;SP\r\n"
    "ESTACAO:;SAO PAULO - MIRANTE\r\n"
    "CODIGO (WMO):;A701\r\n"
    "LATITUDE:;-23,4962888\r\n"
    "LONGITUDE:;-46,6200666\r\n"
    "ALTITUDE:;785,64\r\n"
    "DATA DE FUNDACAO:;25/07/06\r\n"
    "Data;Hora UTC;PRECIPITACAO TOTAL, HORARIO (mm);\r\n"
    "2025/01/01;0000 UTC;0;\r\n"
).encode("latin-1")


@pytest.fixture()
def fixture_zip(tmp_path_factory) -> Path:
    fixtures_dir = tmp_path_factory.mktemp("inmet_service_fixtures")
    zip_path = fixtures_dir / "2025.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(
            "2025/INMET_SE_SP_A701_SAO PAULO - MIRANTE_01-01-2025_A_31-12-2025.CSV",
            SP_CSV,
        )
    return zip_path


class _FakeInmetClient:
    def __init__(self, zip_path: Path, *, base_url=None, timeout_seconds=180) -> None:
        self.base_url = base_url or "https://portal.inmet.gov.br/uploads/dadoshistoricos"
        self._zip_path = zip_path

    def head_content_length(self, year: int) -> int:
        return self._zip_path.stat().st_size

    def download_zip(self, year: int, destination: Path, **_kwargs) -> int:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self._zip_path.read_bytes())
        return destination.stat().st_size


def test_inmet_estacoes_is_registered() -> None:
    service = DownloadService()
    sources = {item.source for item in service.list_sources()}
    assert "inmet_estacoes" in sources


def test_inmet_estacoes_schema_shape() -> None:
    service = DownloadService()
    schema = service.get_source_schema("inmet_estacoes")
    assert schema["source"] == "inmet_estacoes"
    assert schema["mode"] == "inmet portal zip"

    specs = {item["name"]: item for item in schema["params"]}
    assert {
        "output_dir",
        "output_format",
        "start_year",
        "end_year",
        "ufs",
        "variables",
        "keep_raw",
        "timeout",
        "api_base_url",
    } <= set(specs)
    assert specs["start_year"]["required"] is True
    assert specs["start_year"]["minimum"] == 2000
    assert "SP" in specs["ufs"]["allowed_values"]


def test_validate_rejects_unknown_param() -> None:
    service = DownloadService()
    with pytest.raises(ValueError):
        service.validate_source_params(
            "inmet_estacoes", {"start_year": 2025, "bogus": "x"}
        )


def test_validate_requires_start_year() -> None:
    service = DownloadService()
    with pytest.raises(ValueError):
        service.validate_source_params("inmet_estacoes", {"ufs": ["SP"]})


def test_run_end_to_end_with_monkeypatched_client(
    tmp_path: Path, fixture_zip: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        datasource_mod,
        "InmetClient",
        lambda **kwargs: _FakeInmetClient(fixture_zip, **kwargs),
    )
    service = DownloadService()
    result = service.run(
        "inmet_estacoes",
        output_dir=str(tmp_path),
        start_year=2025,
        end_year=2025,
        ufs=["sp"],
        output_format="csv",
    )
    payload = result.to_dict()
    assert payload["source"] == "inmet_estacoes"
    assert payload["status"] == "success"
    assert payload["downloaded_count"] >= 0
    assert len(payload["exported_files"]) == 1
