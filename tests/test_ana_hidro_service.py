"""Tests for ANA HidroWebService registration in the download service."""

from __future__ import annotations

from pathlib import Path

import pytest

from guaraci.ana import hidro as hidro_mod
from guaraci.services.downloads import DownloadService


class _FakeAnaClient:
    base_url = "https://www.ana.gov.br/hidrowebservice"

    def __init__(self, *, identificador: str, senha: str, base_url: str | None = None, timeout_seconds: int = 120) -> None:
        self.identificador = identificador
        self.senha = senha
        if base_url:
            self.base_url = base_url

    def serie_telemetrica(self, *, station_id, detail, data_busca, tipo_filtro_data, range_intervalo):
        return [{"Data_Hora_Medicao": "2024-01-01T00:00:00", "Chuva_Adotada": 1.0}]


def test_ana_hidro_is_registered() -> None:
    service = DownloadService()
    sources = {item.source for item in service.list_sources()}
    assert "ana_hidro" in sources


def test_ana_hidro_schema_shape() -> None:
    service = DownloadService()
    schema = service.get_source_schema("ana_hidro")
    assert schema["mode"] == "ana hidro api"
    specs = {item["name"]: item for item in schema["params"]}
    assert {"station_ids", "start_date", "end_date", "variable", "detail"} <= set(specs)
    assert specs["station_ids"]["required"] is True
    assert specs["variable"]["required"] is True
    assert "chuvas" in specs["variable"]["allowed_values"]
    # Credentials must never be job parameters.
    assert "senha" not in specs
    assert "identificador" not in specs


def test_validate_rejects_unknown_param() -> None:
    service = DownloadService()
    with pytest.raises(ValueError):
        service.validate_source_params(
            "ana_hidro",
            {
                "station_ids": ["1"],
                "start_date": "2024-01-01",
                "end_date": "2024-01-02",
                "variable": "chuvas",
                "senha": "leak",
            },
        )


def test_run_end_to_end_with_monkeypatched_client(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(hidro_mod, "AnaHidroClient", _FakeAnaClient)
    monkeypatch.setenv("GUARACI_ANA_ID", "envid")
    monkeypatch.setenv("GUARACI_ANA_SENHA", "envpass")
    service = DownloadService()
    result = service.run(
        "ana_hidro",
        output_dir=str(tmp_path),
        station_ids=["12345678"],
        start_date="2024-01-01",
        end_date="2024-01-02",
        variable="chuvas",
        output_format="csv",
    )
    payload = result.to_dict()
    assert payload["source"] == "ana_hidro"
    assert payload["status"] == "success"
    assert payload["documents_found"] == 1
    assert len(payload["exported_files"]) == 1


def test_run_missing_credentials_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(hidro_mod, "AnaHidroClient", _FakeAnaClient)
    monkeypatch.delenv("GUARACI_ANA_ID", raising=False)
    monkeypatch.delenv("GUARACI_ANA_SENHA", raising=False)
    service = DownloadService()
    with pytest.raises(ValueError):
        service.run(
            "ana_hidro",
            output_dir=str(tmp_path),
            station_ids=["12345678"],
            start_date="2024-01-01",
            end_date="2024-01-02",
            variable="chuvas",
        )
