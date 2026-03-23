"""Tests for OpenDataSUS datasource DEMAS mode behavior."""

from __future__ import annotations

import json

import pytest

from guaraci.opendatasus.client import OpenDataSUSClientError
from guaraci.opendatasus.datasource import OpenDataSUSDataSource


class _FakeDemasClient:
    mode = "demas"
    base_url = "https://apidadosabertos.saude.gov.br"

    def demas_get(self, path: str, params):  # noqa: ANN001
        offset = int(params.get("offset", 0))
        if path != "/vacinacao/doses-aplicadas-pni-2025":
            return {"doses_aplicadas_pni": []}
        if offset == 0:
            return {
                "doses_aplicadas_pni": [
                    {"codigo_documento": "a", "data_vacina": "2025-01-10 00:00:00-03", "sigla_uf_estabelecimento": "SP"},
                    {"codigo_documento": "b", "data_vacina": "2025-02-01 00:00:00-03", "sigla_uf_estabelecimento": "SP"},
                ]
            }
        if offset == 1:
            return {
                "doses_aplicadas_pni": [
                    {"codigo_documento": "c", "data_vacina": "2025-01-20 00:00:00-03", "sigla_uf_estabelecimento": "RJ"},
                    {"codigo_documento": "d", "data_vacina": "2025-01-25 00:00:00-03", "sigla_uf_estabelecimento": "SP"},
                ]
            }
        return {"doses_aplicadas_pni": []}


class _FakeDemasMixedTypeClient:
    mode = "demas"
    base_url = "https://apidadosabertos.saude.gov.br"

    def demas_get(self, path: str, params):  # noqa: ANN001
        offset = int(params.get("offset", 0))
        if path != "/vacinacao/doses-aplicadas-pni-2025":
            return {"doses_aplicadas_pni": []}
        if offset == 0:
            return {
                "doses_aplicadas_pni": [
                    {
                        "codigo_documento": "a",
                        "data_vacina": "2025-01-10 00:00:00-03",
                        "sigla_uf_estabelecimento": "SP",
                        "descricao_dose_vacina": 1,
                    },
                    {
                        "codigo_documento": "b",
                        "data_vacina": "2025-01-11 00:00:00-03",
                        "sigla_uf_estabelecimento": "SP",
                        "descricao_dose_vacina": "Registro anterior/Transcrição de caderneta",
                    },
                ]
            }
        return {"doses_aplicadas_pni": []}


class _FakeDemasZikavirusClient:
    mode = "demas"
    base_url = "https://apidadosabertos.saude.gov.br"

    def demas_get(self, path: str, params):  # noqa: ANN001
        if path != "/arboviroses/zikavirus":
            return {"arboviroses_zikavirus": []}
        offset = int(params.get("offset", 0))
        if offset == 0:
            return {
                "arboviroses_zikavirus": [
                    {"tp_not": "2", "dt_notific": "2016-01-05", "sg_uf_not": "35"},
                    {"tp_not": "2", "dt_notific": "2016-02-01", "sg_uf_not": "35"},
                ]
            }
        if offset == 1:
            return {
                "arboviroses_zikavirus": [
                    {"tp_not": "2", "dt_notific": "2016-01-12", "sg_uf_not": "29"},
                ]
            }
        return {"arboviroses_zikavirus": []}


def test_download_demas_filters_date_and_uf(tmp_path) -> None:  # noqa: ANN001
    datasource = OpenDataSUSDataSource(
        output_path=str(tmp_path),
        client=_FakeDemasClient(),  # type: ignore[arg-type]
    )

    payload = datasource.download(
        dataset="doses_aplicadas_pni",
        start_year=2025,
        end_year=2025,
        start_date="2025-01-01",
        end_date="2025-01-31",
        uf="SP",
        batch_size=2,
        max_pages=10,
    )

    assert payload["downloaded_count"] == 2
    assert payload["documents_found"] == 2
    assert payload["api_base_url"] == "https://apidadosabertos.saude.gov.br"
    assert payload["raw_file"] is None
    assert payload["keep_raw"] is False

    manifest_path = tmp_path / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["details"]["api_mode"] == "demas"
    assert manifest["details"]["pages_scanned"] == 2
    assert manifest["details"]["truncated"] is False
    assert manifest["raw_file"] is None


def test_download_demas_marks_truncated_when_max_pages_is_reached(tmp_path) -> None:  # noqa: ANN001
    datasource = OpenDataSUSDataSource(
        output_path=str(tmp_path),
        client=_FakeDemasClient(),  # type: ignore[arg-type]
    )

    payload = datasource.download(
        dataset="doses_aplicadas_pni",
        start_year=2025,
        end_year=2025,
        start_date="2025-01-01",
        end_date="2025-01-31",
        uf="SP",
        batch_size=2,
        max_pages=1,
    )

    assert payload["downloaded_count"] == 1
    assert "max_pages" in str(payload.get("export_warning", "")).lower()

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["details"]["truncated"] is True


def test_download_demas_mixed_types_does_not_break_job(tmp_path) -> None:  # noqa: ANN001
    datasource = OpenDataSUSDataSource(
        output_path=str(tmp_path),
        client=_FakeDemasMixedTypeClient(),  # type: ignore[arg-type]
    )

    payload = datasource.download(
        dataset="doses_aplicadas_pni",
        start_year=2025,
        end_year=2025,
        start_date="2025-01-01",
        end_date="2025-01-31",
        uf="SP",
        batch_size=2,
        max_pages=3,
        output_format="csv",
    )

    assert payload["downloaded_count"] == 2
    assert payload["documents_found"] == 2
    assert (payload.get("exported_files") or payload.get("export_warning")) is not None


def test_download_demas_export_error_becomes_warning(tmp_path) -> None:  # noqa: ANN001
    class _BrokenExportDataSource(OpenDataSUSDataSource):
        def export(self, df, format: str, name: str):  # noqa: A003, ANN001
            raise RuntimeError("forced export failure")

    datasource = _BrokenExportDataSource(
        output_path=str(tmp_path),
        client=_FakeDemasClient(),  # type: ignore[arg-type]
    )

    payload = datasource.download(
        dataset="doses_aplicadas_pni",
        start_year=2025,
        end_year=2025,
        start_date="2025-01-01",
        end_date="2025-01-31",
        uf="SP",
        batch_size=2,
        max_pages=3,
        output_format="csv",
    )

    assert payload["downloaded_count"] == 2
    assert payload["exported_files"] == []
    warning = str(payload.get("export_warning", "")).lower()
    assert "export failed after download" in warning
    assert "keep_raw=true" in warning

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["warnings"]


def test_download_demas_failure_adds_endpoint_context(tmp_path) -> None:  # noqa: ANN001
    class _FailingDemasClient:
        mode = "demas"
        base_url = "https://apidadosabertos.saude.gov.br"

        def demas_get(self, path: str, params):  # noqa: ANN001
            raise OpenDataSUSClientError(
                "OpenDataSUS request failed (503): temporarily unavailable",
                category="http_error",
                retryable=True,
                hint="Retry later, reduce the query window, or lower request volume.",
            )

    datasource = OpenDataSUSDataSource(
        output_path=str(tmp_path),
        client=_FailingDemasClient(),  # type: ignore[arg-type]
    )

    with pytest.raises(OpenDataSUSClientError) as excinfo:
        datasource.download(
            dataset="doses_aplicadas_pni",
            start_year=2025,
            end_year=2025,
            batch_size=2,
            max_pages=2,
        )

    message = str(excinfo.value)
    assert "dataset 'doses_aplicadas_pni'" in message
    assert "/vacinacao/doses-aplicadas-pni-2025" in message
    assert "page 1" in message
    assert "retry later" in message.lower()


def test_download_zikavirus_filters_by_date_and_uf_code(tmp_path) -> None:  # noqa: ANN001
    datasource = OpenDataSUSDataSource(
        output_path=str(tmp_path),
        client=_FakeDemasZikavirusClient(),  # type: ignore[arg-type]
    )

    payload = datasource.download(
        dataset="zikavirus",
        start_year=2016,
        end_year=2016,
        start_date="2016-01-01",
        end_date="2016-01-31",
        uf="SP",
        batch_size=2,
        max_pages=5,
    )

    assert payload["downloaded_count"] == 1
    assert payload["documents_found"] == 1
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    endpoints = manifest.get("details", {}).get("endpoints", [])
    assert "/arboviroses/zikavirus" in endpoints


def test_download_demas_keep_raw_true_generates_jsonl(tmp_path) -> None:  # noqa: ANN001
    datasource = OpenDataSUSDataSource(
        output_path=str(tmp_path),
        client=_FakeDemasClient(),  # type: ignore[arg-type]
    )

    payload = datasource.download(
        dataset="doses_aplicadas_pni",
        start_year=2025,
        end_year=2025,
        uf="SP",
        batch_size=2,
        max_pages=2,
        keep_raw=True,
    )

    raw_file = payload.get("raw_file")
    assert isinstance(raw_file, str)
    assert raw_file.endswith(".jsonl")
    assert (tmp_path / "raw").exists()
