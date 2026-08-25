"""Tests for Guaraci HTTP API endpoints."""

from __future__ import annotations

import importlib.util

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("fastapi") is None,
    reason="Requires fastapi to be installed",
)

from fastapi.testclient import TestClient

from guaraci.api import main as api_main
from guaraci.core.results import JobResult


@pytest.fixture()
def client() -> TestClient:
    return TestClient(api_main.app)


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["version"]


def test_ui_endpoint(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "Guaraci" in response.text
    assert "text/html" in response.headers["content-type"]


def test_sources_endpoint(client: TestClient) -> None:
    response = client.get("/sources")

    assert response.status_code == 200
    names = {item["source"] for item in response.json()}
    assert "snis" in names
    assert "sinisa" in names
    assert "doses_aplicadas_pni" in names
    assert "zikavirus" in names
    assert "sinan" in names
    assert "sim" in names
    assert "sih" in names
    assert "nasa_power" in names
    assert "nasa_firms" in names
    assert "nasa_gpm" in names


def test_sources_endpoint_reports_supports_discovery(client: TestClient) -> None:
    response = client.get("/sources")

    assert response.status_code == 200
    payload = response.json()
    by_source = {item["source"]: item["supports_discovery"] for item in payload}

    assert by_source["sih"] is True
    assert by_source["srag_arquivos"] is True
    assert by_source["snis"] is False
    assert sum(1 for value in by_source.values() if value) == 27


def test_nasa_power_schema_endpoint(client: TestClient) -> None:
    response = client.get("/sources/nasa_power/schema")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "nasa_power"
    assert payload["mode"] == "nasa power api"
    names = {item["name"] for item in payload["params"]}
    assert {"latitude", "longitude", "start_date", "end_date", "parameters"} <= names


def test_nasa_firms_schema_endpoint(client: TestClient) -> None:
    response = client.get("/sources/nasa_firms/schema")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "nasa_firms"
    assert payload["mode"] == "nasa firms api"
    names = {item["name"] for item in payload["params"]}
    assert {"start_date", "end_date", "product", "country"} <= names
    # The MAP_KEY must never be exposed as a job parameter.
    assert "map_key" not in names


def test_nasa_gpm_schema_endpoint(client: TestClient) -> None:
    response = client.get("/sources/nasa_gpm/schema")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "nasa_gpm"
    assert payload["mode"] == "nasa gpm api"
    names = {item["name"] for item in payload["params"]}
    assert {"latitude", "longitude", "start_date", "end_date", "variable"} <= names
    # The Earthdata token must never be exposed as a job parameter.
    assert "token" not in names


def test_source_schema_endpoint(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        api_main.download_service,
        "get_source_schema",
        lambda source: {
            "source": source,
            "title": "SNIS",
            "mode": "gov.br crawl",
            "params": [
                {
                    "name": "timeout",
                    "type": "integer",
                    "description": "HTTP timeout in seconds.",
                    "required": False,
                    "default": 120,
                    "allowed_values": None,
                    "minimum": 1,
                    "maximum": None,
                }
            ],
        },
    )

    response = client.get("/sources/snis/schema")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "snis"
    assert payload["params"][0]["name"] == "timeout"


def test_source_schema_endpoint_not_found(client: TestClient, monkeypatch) -> None:
    def fake_schema(source: str):  # noqa: ARG001
        raise ValueError("Unsupported source")

    monkeypatch.setattr(api_main.download_service, "get_source_schema", fake_schema)

    response = client.get("/sources/unknown/schema")
    assert response.status_code == 404


def test_source_discovery_endpoint(client: TestClient, monkeypatch) -> None:
    def fake_discover(source: str, **kwargs):  # noqa: ANN003
        assert source == "sih"
        assert kwargs["months"] == ["1"]
        return {
            "source": "sih",
            "documents_found": 1,
            "total_size_bytes": 237472,
            "by_group": {"RD": 1},
            "by_state": {"AC": 1},
            "sample": [{"name": "RDAC1901.dbc"}],
            "filters": kwargs,
        }

    monkeypatch.setattr(api_main.download_service, "discover", fake_discover)

    response = client.post(
        "/sources/sih/discovery",
        json={
            "params": {
                "start_year": 2019,
                "end_year": 2019,
                "groups": ["RD"],
                "states": ["AC"],
                "months": ["1"],
            }
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["documents_found"] == 1
    assert payload["total_size_bytes"] == 237472
    assert payload["sample"][0]["name"] == "RDAC1901.dbc"


def test_source_discovery_endpoint_ftp_source(client: TestClient, monkeypatch) -> None:
    """Exercise the real FTP service-discover branch (only the FTP backend faked)."""
    from guaraci.datasus import ftp_source as ftp_source_mod

    def fake_summary(spec, **kwargs):  # noqa: ANN003
        assert spec.name == "sia"
        assert kwargs["fetch_sizes"] is False
        return {
            "source": "sia",
            "documents_found": 2,
            "total_size_bytes": 0,
            "by_group": {"PA": 2},
            "by_state": {"SP": 2},
            "sample": [],
            "filters": {},
        }

    monkeypatch.setattr(ftp_source_mod.generic_backend, "discover_summary", fake_summary)

    response = client.post(
        "/sources/sia/discovery",
        json={
            "params": {
                "start_year": 2024,
                "end_year": 2024,
                "groups": ["PA"],
                "states": ["SP"],
            }
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["documents_found"] == 2
    assert payload["by_group"] == {"PA": 2}


def test_source_discovery_endpoint_returns_bad_request(client: TestClient, monkeypatch) -> None:
    def fake_discover(source: str, **kwargs):  # noqa: ARG001, ANN003
        raise ValueError("Discovery is not supported")

    monkeypatch.setattr(api_main.download_service, "discover", fake_discover)

    response = client.post("/sources/snis/discovery", json={"params": {}})

    assert response.status_code == 400


def test_source_schema_endpoint_sinan_contains_expected_fields(client: TestClient) -> None:
    response = client.get("/sources/sinan/schema")

    assert response.status_code == 200
    payload = response.json()
    names = {item["name"] for item in payload["params"]}
    assert payload["source"] == "sinan"
    assert payload["mode"] == "pysus ftp"
    assert {"start_year", "end_year", "diseases", "output_format"} <= names
    assert "ano" not in names


def test_source_schema_endpoint_sih_uses_empty_selection_as_unfiltered(client: TestClient) -> None:
    response = client.get("/sources/sih/schema")

    assert response.status_code == 200
    payload = response.json()
    specs = {item["name"]: item for item in payload["params"]}
    assert {"groups", "months"} <= set(specs)
    assert specs["groups"]["default"] is None
    assert specs["months"]["default"] is None
    assert "Leave empty" in specs["groups"]["description"]
    assert "Leave empty" in specs["months"]["description"]
    assert "mes" not in specs


def test_source_schema_endpoint_doses_aplicadas_pni_contains_expected_fields(client: TestClient) -> None:
    response = client.get("/sources/doses_aplicadas_pni/schema")

    assert response.status_code == 200
    payload = response.json()
    names = {item["name"] for item in payload["params"]}
    assert payload["source"] == "doses_aplicadas_pni"
    assert payload["mode"] == "opendatasus api"
    assert {"start_year", "end_year", "uf", "output_format", "keep_raw"} <= names
    assert "dataset" not in names


def test_source_schema_endpoint_removed_vacinacao_alias_returns_not_found(
    client: TestClient,
) -> None:
    response = client.get("/sources/vacinacao_covid19/schema")

    assert response.status_code == 404


@pytest.mark.parametrize("source_name", [
    "zikavirus",
    "febre_amarela",
    "dengue",
    "chikungunya",
    "srag_demas",
    "sindrome_gripal_leve",
    "mpox",
    "esavi",
])
def test_source_schema_endpoint_epidemiological_sources_contains_expected_fields(client: TestClient, source_name: str) -> None:
    response = client.get(f"/sources/{source_name}/schema")

    assert response.status_code == 200
    payload = response.json()
    names = {item["name"] for item in payload["params"]}
    assert payload["source"] == source_name
    assert payload["mode"] == "opendatasus api"
    assert {"start_year", "end_year", "uf", "output_format", "batch_size", "max_pages", "keep_raw"} <= names


def test_source_schema_endpoint_autogenerated_opendatasus_contains_native_filters(
    client: TestClient,
) -> None:
    response = client.get("/sources/cnes_estabelecimentos/schema")

    assert response.status_code == 200
    payload = response.json()
    specs = {item["name"]: item for item in payload["params"]}
    assert payload["source"] == "cnes_estabelecimentos"
    assert payload["mode"] == "opendatasus api"
    assert specs["codigo_uf"]["phase"] == "basico"
    assert specs["status"]["phase"] == "basico"
    assert {"output_dir", "output_format", "keep_raw", "batch_size", "max_pages"} <= set(specs)


def test_download_snis_endpoint(client: TestClient, monkeypatch) -> None:
    def fake_download_snis(**kwargs):  # noqa: ANN003
        return JobResult(
            source="snis",
            documents_found=4,
            downloaded_count=3,
            skipped_count=1,
            failed_count=0,
            manifest_path="data/snis/manifest.json",
        )

    monkeypatch.setattr(api_main.download_service, "download_snis", fake_download_snis)

    response = client.post("/downloads/snis", json={"file_kinds": ["planilhas"]})

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "snis"
    assert payload["status"] == "success"
    assert payload["downloaded_count"] == 3


def test_create_job_endpoint(client: TestClient, monkeypatch) -> None:
    class DummyJob:
        def to_dict(self):
            return {
                "job_id": "job-123",
                "source": "snis",
                "params": {"file_kinds": ["planilhas"]},
                "status": "queued",
                "progress": 0.0,
                "created_at": "2026-02-22T00:00:00+00:00",
                "started_at": None,
                "finished_at": None,
                "result": None,
                "error": None,
            }

    monkeypatch.setattr(
        api_main.job_service,
        "create_job",
        lambda **kwargs: DummyJob(),  # type: ignore[arg-type]
    )

    response = client.post(
        "/jobs",
        json={"source": "snis", "params": {"file_kinds": ["planilhas"]}},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["job_id"] == "job-123"
    assert payload["status"] == "queued"


def test_create_job_endpoint_rejects_invalid_params(client: TestClient) -> None:
    response = client.post(
        "/jobs",
        json={"source": "snis", "params": {"invalid_param": True}},
    )

    assert response.status_code == 400
    assert "unsupported parameter" in response.json()["detail"].lower()


def test_get_job_endpoint_not_found(client: TestClient, monkeypatch) -> None:
    def fake_get_job(job_id: str):  # noqa: ARG001
        raise KeyError("not found")

    monkeypatch.setattr(api_main.job_service, "get_job", fake_get_job)

    response = client.get("/jobs/missing")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_cancel_job_endpoint(client: TestClient, monkeypatch) -> None:
    class DummyJob:
        def to_dict(self):
            return {
                "job_id": "job-1",
                "source": "snis",
                "params": {},
                "status": "cancel_requested",
                "progress": 0.0,
                "created_at": "2026-02-22T00:00:00+00:00",
                "started_at": "2026-02-22T00:00:01+00:00",
                "finished_at": None,
                "result": None,
                "error": "Cancellation requested by user.",
                "cancel_requested": True,
                "attempt": 1,
                "retry_of": None,
            }

    monkeypatch.setattr(
        api_main.job_service,
        "cancel_job",
        lambda **kwargs: DummyJob(),  # type: ignore[arg-type]
    )

    response = client.post("/jobs/job-1/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "cancel_requested"


def test_cancel_job_endpoint_not_found(client: TestClient, monkeypatch) -> None:
    def fake_cancel_job(job_id: str):  # noqa: ARG001
        raise KeyError("not found")

    monkeypatch.setattr(api_main.job_service, "cancel_job", fake_cancel_job)

    response = client.post("/jobs/missing/cancel")
    assert response.status_code == 404


def test_retry_job_endpoint(client: TestClient, monkeypatch) -> None:
    class DummyJob:
        def to_dict(self):
            return {
                "job_id": "job-2",
                "source": "snis",
                "params": {},
                "status": "queued",
                "progress": 0.0,
                "created_at": "2026-02-22T00:00:00+00:00",
                "started_at": None,
                "finished_at": None,
                "result": None,
                "error": None,
                "cancel_requested": False,
                "attempt": 2,
                "retry_of": "job-1",
            }

    monkeypatch.setattr(
        api_main.job_service,
        "retry_job",
        lambda **kwargs: DummyJob(),  # type: ignore[arg-type]
    )

    response = client.post("/jobs/job-1/retry")
    assert response.status_code == 202
    payload = response.json()
    assert payload["attempt"] == 2
    assert payload["retry_of"] == "job-1"


def test_retry_job_endpoint_rejects_invalid_state(client: TestClient, monkeypatch) -> None:
    def fake_retry_job(job_id: str):  # noqa: ARG001
        raise ValueError("Cannot retry this status")

    monkeypatch.setattr(api_main.job_service, "retry_job", fake_retry_job)

    response = client.post("/jobs/job-1/retry")
    assert response.status_code == 400


def test_job_logs_endpoint(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        api_main.job_service,
        "get_job_logs",
        lambda **kwargs: [  # type: ignore[arg-type]
            {
                "timestamp_utc": "2026-02-22T00:00:00+00:00",
                "event": "file_completed",
                "level": "info",
                "message": "Downloaded file.zip",
            }
        ],
    )

    response = client.get("/jobs/job-1/logs?limit=10")
    assert response.status_code == 200
    assert response.json()[0]["event"] == "file_completed"


def test_job_output_endpoint(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        api_main.job_service,
        "get_job_output_info",
        lambda **kwargs: {  # type: ignore[arg-type]
            "job_id": "job-1",
            "status": "completed",
            "output_dir": "data/snis",
            "manifest_path": "data/snis/manifest.json",
            "available": True,
        },
    )

    response = client.get("/jobs/job-1/output")
    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["output_dir"] == "data/snis"


def test_open_output_endpoint_not_opened(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        api_main.job_service,
        "open_job_output_dir",
        lambda **kwargs: {  # type: ignore[arg-type]
            "opened": False,
            "output_dir": "data/snis",
            "message": "Running in Docker: open folder from host using the path shown above.",
        },
    )

    response = client.post("/jobs/job-1/open-output")
    assert response.status_code == 200
    assert response.json()["opened"] is False


def test_open_output_endpoint_success(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        api_main.job_service,
        "open_job_output_dir",
        lambda **kwargs: {  # type: ignore[arg-type]
            "opened": True,
            "output_dir": "data/snis",
            "message": "Folder open command executed.",
        },
    )

    response = client.post("/jobs/job-1/open-output")
    assert response.status_code == 200
    assert response.json()["opened"] is True


def test_list_jobs_endpoint(client: TestClient, monkeypatch) -> None:
    class DummyJob:
        def __init__(self, job_id: str):
            self._job_id = job_id

        def to_dict(self):
            return {
                "job_id": self._job_id,
                "source": "snis",
                "params": {},
                "status": "completed",
                "progress": 100.0,
                "created_at": "2026-02-22T00:00:00+00:00",
                "started_at": "2026-02-22T00:00:01+00:00",
                "finished_at": "2026-02-22T00:00:02+00:00",
                "result": {
                    "source": "snis",
                    "status": "success",
                    "documents_found": 1,
                    "downloaded_count": 1,
                    "skipped_count": 0,
                    "failed_count": 0,
                    "manifest_path": "data/snis/manifest.json",
                },
                "error": None,
            }

    monkeypatch.setattr(
        api_main.job_service,
        "list_jobs",
        lambda **kwargs: [DummyJob("job-a"), DummyJob("job-b")],  # type: ignore[arg-type]
    )

    response = client.get("/jobs?limit=2")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert {item["job_id"] for item in payload} == {"job-a", "job-b"}
